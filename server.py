import asyncio
import ipaddress
import json
import os
import queue
import socket
import ssl
import sys
import threading
import time
from array import array
from datetime import datetime, timedelta, timezone

import pyaudiowpatch as pyaudio
import qrcode
from aiohttp import WSCloseCode, WSMsgType, web
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtensionOID, NameOID

PORT = 8443
HTTP_PORT = 8080      # puerto sin TLS para la app Android (HTTP + WebSocket + UDP Discovery)
HEARTBEAT_SEC = 10    # ping al celular; si no responde, cierra sesiones zombi
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FROZEN = getattr(sys, "frozen", False)
APP_DIR = os.path.dirname(sys.executable) if FROZEN else BASE_DIR
RES_DIR = getattr(sys, "_MEIPASS", BASE_DIR)

VBCABLE_KEYWORDS = ("cable input", "vb-audio", "voicemeeter input", "voice meeter input")

mic_queue = queue.Queue(maxsize=40)
main_loop = None
active_ws = None
pc_queue = None


def _ip_priority(ip_str: str) -> int:
    """Prioriza IPs LAN domésticas/hotspot reales sobre adaptadores VPN/virtuales."""
    if ip_str.startswith("192.168."):
        return 0
    if ip_str.startswith("10."):
        return 1
    if ip_str.startswith("172."):
        try:
            second = int(ip_str.split(".")[1])
            if 16 <= second <= 31:
                return 2
        except Exception:
            pass
    return 3


def get_all_local_ips():
    """Devuelve todas las direcciones IPv4 privadas activas de la PC ordenadas por prioridad LAN."""
    ips = []
    for target in (("192.168.1.1", 80), ("192.168.0.1", 80), ("192.168.137.1", 80), ("192.168.43.1", 80), ("8.8.8.8", 80)):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(target)
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127.") and not ip.startswith("169.254.") and ip not in ips:
                ips.append(ip)
        except Exception:
            pass
    try:
        _, _, host_ips = socket.gethostbyname_ex(socket.gethostname())
        for ip in host_ips:
            if ip and not ip.startswith("127.") and not ip.startswith("169.254.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    ips.sort(key=_ip_priority)
    return ips or ["127.0.0.1"]


def get_local_ip():
    return get_all_local_ips()[0]


class UdpDiscoveryProtocol(asyncio.DatagramProtocol):
    """Responde a paquetes UDP Broadcast de autodescubrimiento enviados por la app Android."""
    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if data and b"NEXOAUDIO_DISCOVER" in data and self.transport:
            reply = json.dumps({"app": "nexoaudio", "port": HTTP_PORT}).encode("utf-8")
            try:
                self.transport.sendto(reply, addr)
            except Exception:
                pass


def _cert_matches_ip(cert_path: str, local_ip: str) -> bool:
    try:
        with open(cert_path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        now = datetime.now(timezone.utc)
        not_after = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after.replace(tzinfo=timezone.utc)
        if not_after <= now:
            return False
        target_ip = ipaddress.ip_address(local_ip)
        san = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value
        return target_ip in san.get_values_for_type(x509.IPAddress)
    except Exception:
        return False


def ensure_ssl_certs(local_ip, cert_path=os.path.join(APP_DIR, "cert.pem"), key_path=os.path.join(APP_DIR, "key.pem")):
    if os.path.exists(cert_path) and os.path.exists(key_path) and _cert_matches_ip(cert_path, local_ip):
        return cert_path, key_path

    print(f"[*] Generando certificado HTTPS local para {local_ip}...")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "NexoAudio")])
    now = datetime.now(timezone.utc)

    san_list = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    ]
    seen_ips = {ipaddress.ip_address("127.0.0.1")}
    for ip_str in [local_ip] + get_all_local_ips():
        try:
            ip_obj = ipaddress.ip_address(ip_str)
            if ip_obj not in seen_ips:
                seen_ips.add(ip_obj)
                san_list.append(x509.IPAddress(ip_obj))
        except ValueError:
            pass

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(san_list), critical=False)
        .sign(key, hashes.SHA256())
    )

    with open(key_path, "wb") as f:
        f.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    return cert_path, key_path


def is_vbcable_name(name: str) -> bool:
    low = (name or "").lower()
    return any(k in low for k in VBCABLE_KEYWORDS)


def find_vbcable_devices(p: pyaudio.PyAudio):
    """Lista salidas VB-Cable priorizando WASAPI > DirectSound > MME."""
    api_order = {}
    for rank, api_type in enumerate((pyaudio.paWASAPI, pyaudio.paDirectSound, pyaudio.paMME)):
        try:
            api_order[p.get_host_api_info_by_type(api_type)["index"]] = rank
        except Exception:
            pass

    found = []
    for i in range(p.get_device_count()):
        dev = p.get_device_info_by_index(i)
        if dev.get("maxOutputChannels", 0) <= 0 or dev.get("isLoopbackDevice", False):
            continue
        name = dev.get("name", "").lower()
        if "cable output" in name:
            continue
        if any(k in name for k in VBCABLE_KEYWORDS):
            found.append(dev)

    found.sort(key=lambda d: api_order.get(d.get("hostApi"), 99))
    return found


def drain(q, empty_exc):
    while True:
        try:
            q.get_nowait()
        except empty_exc:
            return


def broadcast_pc_audio(data: bytes):
    """Encola audio de la PC hacia el celular activo descartando paquetes viejos si hay atasco."""
    q = pc_queue
    if q is None:
        return
    if q.full():
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            pass
    try:
        q.put_nowait(data)
    except asyncio.QueueFull:
        pass


def float32_to_int16(raw_bytes: bytes) -> array:
    floats = array("f")
    floats.frombytes(raw_bytes[: len(raw_bytes) & ~3])
    out = array("h", (max(-32768, min(32767, int(v * 32767.0))) for v in floats))
    return out


def int16_to_float32_bytes(samples: array) -> bytes:
    out = array("f", (v / 32768.0 for v in samples))
    return out.tobytes()


def normalize_pc_audio(raw_bytes: bytes, fmt: int, channels: int, decim: int) -> bytes:
    """Convierte audio capturado de la PC a Int16 estéreo y reduce 96k/192k para no saturar el Wi-Fi."""
    if fmt == pyaudio.paInt16 and channels == 2 and decim == 1:
        return raw_bytes

    if fmt == pyaudio.paFloat32:
        samples = float32_to_int16(raw_bytes)
    else:
        samples = array("h")
        samples.frombytes(raw_bytes[: len(raw_bytes) & ~1])

    total = len(samples)
    if total == 0:
        return b""

    if channels == 1:
        stereo = array("h", [0]) * (total * 2)
        stereo[0::2] = samples
        stereo[1::2] = samples
    elif channels == 2:
        stereo = samples
    elif channels >= 6:
        frames = total // channels
        stereo = array("h", [0]) * (frames * 2)
        has_side = channels >= 8
        for i in range(frames):
            o = i * channels
            c = samples[o + 2] * 0.7071
            l_val = samples[o] + c + samples[o + 4] * 0.7071
            r_val = samples[o + 1] + c + samples[o + 5] * 0.7071
            if has_side:
                l_val += samples[o + 6] * 0.7071
                r_val += samples[o + 7] * 0.7071
                scale = 0.45
            else:
                scale = 0.58
            stereo[i * 2] = max(-32768, min(32767, int(l_val * scale)))
            stereo[i * 2 + 1] = max(-32768, min(32767, int(r_val * scale)))
    else:
        frames = total // channels
        stereo = array("h", [0]) * (frames * 2)
        for i in range(frames):
            o = i * channels
            stereo[i * 2] = samples[o]
            stereo[i * 2 + 1] = samples[o + 1]

    if decim > 1:
        step = 2 * decim
        l_ch = stereo[0::step]
        r_ch = stereo[1::step]
        n_out = min(len(l_ch), len(r_ch))
        reduced = array("h", [0]) * (n_out * 2)
        reduced[0::2] = l_ch[:n_out]
        reduced[1::2] = r_ch[:n_out]
        return reduced.tobytes()

    return stereo.tobytes()


class AudioEngine:
    def __init__(self):
        self.p = None
        self.loopback_stream = None
        self.mic_stream = None
        self._mic_lock = threading.Lock()
        self._worker_started = False

        # Estado de captura de PC
        self.loopback_dev = None
        self.loopback_is_vbcable = False
        self.pc_fmt = pyaudio.paInt16
        self.pc_raw_rate = 48000
        self.pc_raw_channels = 2
        self.pc_decim = 1
        self.pc_rate = 48000       # frecuencia efectiva enviada al celular
        self.pc_channels = 2       # siempre enviamos estéreo al celular

        # Estado de micrófono virtual (VB-Cable)
        self.cable_dev = None
        self.mic_fmt = pyaudio.paInt16
        self.mic_rate = 48000
        self.mic_channels = 2
        self.client_rate = 48000

        # Estado del resampler y diagnóstico de señal
        self.resample_pos = 0.0
        self.prev_sample = 0
        self._seen_pc_signal = False
        self._seen_mic_signal = False
        self._last_mic_reopen = 0.0

    def reset_session_state(self):
        self.resample_pos = 0.0
        self.prev_sample = 0
        self._seen_pc_signal = False
        self._seen_mic_signal = False

    def _compute_decim(self, rate: int):
        """Reduce frecuencias de estudio (96k/192k/88.2k/176.4k) a <=48k para evitar cortes por Wi-Fi."""
        for factor in (4, 2):
            if rate > 48000 and rate % factor == 0 and (rate // factor) <= 48000:
                return factor, rate // factor
        return 1, rate

    def _get_candidate_loopbacks(self):
        candidates = []
        default_lb = None
        try:
            default_lb = self.p.get_default_wasapi_loopback()
            if default_lb:
                candidates.append(default_lb)
        except Exception as e:
            print(f"[!] No se pudo obtener el altavoz WASAPI predeterminado: {e}")

        try:
            for dev in self.p.get_loopback_device_info_generator():
                if not default_lb or dev["index"] != default_lb["index"]:
                    candidates.append(dev)
        except Exception:
            pass
        return candidates

    def _open_loopback_stream(self):
        def loopback_callback(in_data, frame_count, time_info, status):
            if pc_queue is not None and main_loop is not None:
                try:
                    main_loop.call_soon_threadsafe(broadcast_pc_audio, in_data)
                except RuntimeError:
                    pass
            return (None, pyaudio.paContinue)

        for dev in self._get_candidate_loopbacks():
            raw_rate = int(dev.get("defaultSampleRate", 48000)) or 48000
            max_ch = max(1, int(dev.get("maxInputChannels", 2)))
            chunk_20ms = max(480, int(raw_rate * 0.02))
            ch_options = list(dict.fromkeys([max_ch, 2, 1]))
            ch_options = [c for c in ch_options if 1 <= c <= max_ch]

            for fmt in (pyaudio.paInt16, pyaudio.paFloat32):
                for ch in ch_options:
                    for fpb in (chunk_20ms, 0):
                        try:
                            stream = self.p.open(
                                format=fmt,
                                channels=ch,
                                rate=raw_rate,
                                input=True,
                                start=False,
                                frames_per_buffer=fpb,
                                input_device_index=dev["index"],
                                stream_callback=loopback_callback,
                            )
                        except Exception:
                            continue

                        decim, eff_rate = self._compute_decim(raw_rate)
                        self.loopback_dev = dev
                        self.loopback_is_vbcable = is_vbcable_name(dev.get("name", ""))
                        self.pc_fmt = fmt
                        self.pc_raw_rate = raw_rate
                        self.pc_raw_channels = ch
                        self.pc_decim = decim
                        self.pc_rate = eff_rate
                        self.pc_channels = 2
                        self.loopback_stream = stream
                        return True
        return False

    def _open_mic_stream(self):
        """Abre VB-Cable priorizando WASAPI con su frecuencia y canales nativos (evita errores en otras PCs)."""
        try:
            wasapi_idx = self.p.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]
        except Exception:
            wasapi_idx = None

        for dev in find_vbcable_devices(self.p):
            default_rate = int(dev.get("defaultSampleRate", 48000)) or 48000
            max_ch = max(1, int(dev.get("maxOutputChannels", 2)))
            is_wasapi = dev.get("hostApi") == wasapi_idx

            # En WASAPI compartido conviene abrir primero en la frecuencia nativa configurada en Windows
            candidate_rates = list(dict.fromkeys([default_rate, 48000, 44100]))
            candidate_ch = list(dict.fromkeys([c for c in (2, 1, max_ch) if 1 <= c <= max_ch]))

            for fmt in (pyaudio.paInt16, pyaudio.paFloat32):
                for rate in candidate_rates:
                    frames = max(480, int(rate * (0.02 if is_wasapi else 0.04)))
                    for ch in candidate_ch:
                        for fpb in (frames, 0):
                            try:
                                stream = self.p.open(
                                    format=fmt,
                                    channels=ch,
                                    rate=rate,
                                    output=True,
                                    start=False,
                                    frames_per_buffer=fpb,
                                    output_device_index=dev["index"],
                                )
                            except Exception:
                                continue
                            self.cable_dev = dev
                            self.mic_fmt = fmt
                            self.mic_rate = rate
                            self.mic_channels = ch
                            self.mic_stream = stream
                            return True
        return False

    def start(self):
        self.p = pyaudio.PyAudio()

        if self._open_loopback_stream():
            fmt_name = "Float32" if self.pc_fmt == pyaudio.paFloat32 else "Int16"
            print(
                f"[OK] Captura de PC lista (Loopback): {self.loopback_dev['name']} "
                f"({self.pc_raw_rate}Hz -> {self.pc_rate}Hz, {self.pc_raw_channels}ch -> 2ch, {fmt_name})"
            )
            if self.loopback_is_vbcable:
                print(
                    "[!] ALERTA: Tu altavoz predeterminado en Windows es VB-Cable ('CABLE Input').\n"
                    "    Eso causa eco o silencio. Cambia la salida de Windows a tus Altavoces/Audífonos reales\n"
                    "    y vuelve a abrir NexoAudio."
                )
        else:
            print(
                "[!] ERROR: No se pudo abrir ningún dispositivo de captura WASAPI Loopback.\n"
                "    Verifica en Windows que tengas un dispositivo de salida de audio activo (altavoces/audífonos)."
            )

        if self._open_mic_stream():
            api = self.p.get_host_api_info_by_index(self.cable_dev["hostApi"])["name"]
            fmt_name = "Float32" if self.mic_fmt == pyaudio.paFloat32 else "Int16"
            print(
                f"[OK] Micrófono Virtual conectado: {self.cable_dev['name']} "
                f"[{api}] ({self.mic_rate}Hz, {self.mic_channels}ch, {fmt_name})"
            )
        else:
            print(
                "[!] AVISO: No se detectó o no se pudo abrir 'CABLE Input' (VB-Cable).\n"
                "    Si quieres usar el micrófono del celular, instala VB-Cable y REINICIA la PC."
            )

        if not self._worker_started:
            self._worker_started = True
            threading.Thread(target=self._mic_writer_worker, daemon=True).start()

    def set_streams_active(self, active: bool):
        if self.loopback_stream:
            try:
                if active and self.loopback_stream.is_stopped():
                    self.loopback_stream.start_stream()
                elif not active and self.loopback_stream.is_active():
                    self.loopback_stream.stop_stream()
            except Exception as e:
                print(f"[!] Error cambiando estado de Loopback: {e}")

        with self._mic_lock:
            if self.mic_stream:
                try:
                    if active and self.mic_stream.is_stopped():
                        self.mic_stream.start_stream()
                    elif not active and self.mic_stream.is_active():
                        self.mic_stream.stop_stream()
                except Exception:
                    pass

    def process_mic_chunk(self, raw_bytes: bytes, in_rate: int) -> bytes:
        """Adapta el audio mono Int16 del celular a la frecuencia, canales y formato exactos de VB-Cable."""
        out_rate = self.mic_rate
        out_ch = self.mic_channels

        samples = array("h")
        samples.frombytes(raw_bytes)
        n_in = len(samples)
        if n_in == 0:
            return b""

        if not self._seen_mic_signal:
            peak = max(abs(min(samples)), abs(max(samples)))
            if peak > 120:
                self._seen_mic_signal = True
                print("[OK] Señal de voz recibida desde el celular -> enviando a VB-Cable.")

        if in_rate == out_rate:
            mono = samples
        else:
            step = in_rate / out_rate
            pos = self.resample_pos
            prev = self.prev_sample
            mono = array("h")
            append = mono.append
            while pos < n_in:
                idx = int(pos)
                frac = pos - idx
                s0 = prev if idx == 0 else samples[idx - 1]
                s1 = samples[idx]
                append(max(-32768, min(32767, int(s0 + frac * (s1 - s0)))))
                pos += step
            self.resample_pos = pos - n_in
            self.prev_sample = samples[-1]

        n_out = len(mono)
        if n_out == 0:
            return b""

        if out_ch == 1:
            final_samples = mono
        elif out_ch == 2:
            final_samples = array("h", [0]) * (n_out * 2)
            final_samples[0::2] = mono
            final_samples[1::2] = mono
        else:
            final_samples = array("h", [0]) * (n_out * out_ch)
            final_samples[0::out_ch] = mono
            final_samples[1::out_ch] = mono

        if self.mic_fmt == pyaudio.paFloat32:
            return int16_to_float32_bytes(final_samples)
        return final_samples.tobytes()

    def _try_reopen_mic_stream_locked(self):
        now = time.monotonic()
        if now - self._last_mic_reopen < 2.0 or self.p is None:
            return
        self._last_mic_reopen = now
        if self.mic_stream:
            try:
                self.mic_stream.stop_stream()
                self.mic_stream.close()
            except Exception:
                pass
            self.mic_stream = None
        if self._open_mic_stream():
            try:
                self.mic_stream.start_stream()
                print(f"[*] Micrófono virtual recuperado: {self.cable_dev['name']} ({self.mic_rate}Hz, {self.mic_channels}ch)")
            except Exception:
                pass

    def _mic_writer_worker(self):
        last_err = None
        while True:
            data = mic_queue.get()
            if data is None:
                break
            with self._mic_lock:
                if self.mic_stream is None:
                    continue
                try:
                    if self.mic_stream.is_stopped():
                        self.mic_stream.start_stream()
                    out = self.process_mic_chunk(data, self.client_rate)
                    if out:
                        self.mic_stream.write(out)
                except Exception as e:
                    if repr(e) != last_err:
                        last_err = repr(e)
                        print(f"[!] Error escribiendo a VB-Cable: {e!r} (reintentando abrir stream...)")
                    self._try_reopen_mic_stream_locked()

    def convert_pc_packet(self, raw_bytes: bytes) -> bytes:
        out = normalize_pc_audio(raw_bytes, self.pc_fmt, self.pc_raw_channels, self.pc_decim)
        if not self._seen_pc_signal and len(out) >= 4:
            probe = array("h")
            probe.frombytes(out[: min(len(out), 256)])
            if probe and max(abs(min(probe)), abs(max(probe))) > 40:
                self._seen_pc_signal = True
                print("[OK] Señal de audio de la PC detectada -> transmitiendo al celular.")
        return out

    def stop(self):
        try:
            mic_queue.put_nowait(None)
        except queue.Full:
            pass
        if self.loopback_stream:
            try:
                if self.loopback_stream.is_active():
                    self.loopback_stream.stop_stream()
                self.loopback_stream.close()
            except Exception:
                pass
        with self._mic_lock:
            if self.mic_stream:
                try:
                    self.mic_stream.stop_stream()
                    self.mic_stream.close()
                except Exception:
                    pass
                self.mic_stream = None
        if self.p:
            try:
                self.p.terminate()
            except Exception:
                pass


audio_engine = AudioEngine()


async def index_handler(request):
    return web.FileResponse(os.path.join(RES_DIR, "index.html"))


PING_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Private-Network": "true",
    "Cache-Control": "no-store",
}


async def ping_handler(request):
    if request.method == "OPTIONS":
        return web.Response(status=204, headers=PING_HEADERS)
    sockname = request.transport.get_extra_info("sockname") if request.transport else None
    actual_ip = sockname[0] if sockname and isinstance(sockname, tuple) and sockname[0] != "0.0.0.0" else get_local_ip()
    return web.json_response({"app": "nexoaudio", "ip": actual_ip}, headers=PING_HEADERS)


async def websocket_handler(request):
    global active_ws, pc_queue

    ws = web.WebSocketResponse(heartbeat=HEARTBEAT_SEC, max_msg_size=1 << 17)
    await ws.prepare(request)

    if request.transport is not None:
        raw_sock = request.transport.get_extra_info("socket")
        if raw_sock is not None:
            try:
                raw_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except Exception:
                pass

    q = asyncio.Queue(maxsize=40)

    old, active_ws, pc_queue = active_ws, ws, q
    if old is not None and not old.closed:
        print("[*] Nueva conexión: reemplazando la sesión anterior")
        try:
            await asyncio.wait_for(old.close(code=WSCloseCode.GOING_AWAY, message=b"replaced"), 2)
        except Exception:
            pass

    drain(mic_queue, queue.Empty)
    audio_engine.client_rate = 48000
    audio_engine.reset_session_state()
    audio_engine.set_streams_active(True)
    print(f"[+] Celular conectado desde {request.remote}")

    await ws.send_str(
        json.dumps(
            {
                "type": "config",
                "pc_rate": audio_engine.pc_rate,
                "pc_channels": audio_engine.pc_channels,
                "mic_rate": audio_engine.mic_rate,
                "mic_channels": audio_engine.mic_channels,
                "loopback_active": audio_engine.loopback_stream is not None,
                "loopback_is_vbcable": audio_engine.loopback_is_vbcable,
                "vbcable_active": audio_engine.mic_stream is not None,
            }
        )
    )
    drain(q, asyncio.QueueEmpty)

    async def send_pc_audio_loop():
        try:
            while not ws.closed:
                raw = await q.get()
                payload = audio_engine.convert_pc_packet(raw)
                if payload:
                    await ws.send_bytes(payload)
        except Exception:
            pass

    sender_task = asyncio.create_task(send_pc_audio_loop())

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    info = json.loads(msg.data)
                    if info.get("type") == "client_config":
                        rate = int(info.get("mic_rate", 48000))
                        if 8000 <= rate <= 192000:
                            audio_engine.client_rate = rate
                            audio_engine.resample_pos = 0.0
                            audio_engine.prev_sample = 0
                            print(f"[*] Micrófono del celular a {rate}Hz -> Salida VB-Cable a {audio_engine.mic_rate}Hz")
                except Exception:
                    pass

            elif msg.type == WSMsgType.BINARY and audio_engine.mic_stream is not None:
                raw = msg.data[: len(msg.data) & ~1]
                if not raw:
                    continue
                if mic_queue.full():
                    try:
                        mic_queue.get_nowait()
                    except queue.Empty:
                        pass
                try:
                    mic_queue.put_nowait(raw)
                except queue.Full:
                    pass
    finally:
        sender_task.cancel()
        if active_ws is ws:
            active_ws, pc_queue = None, None
            audio_engine.set_streams_active(False)
        print(f"[-] Celular desconectado ({request.remote})")

    return ws


async def main():
    global main_loop
    main_loop = asyncio.get_running_loop()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    local_ip = get_local_ip()
    all_ips = get_all_local_ips()
    cert_file, key_file = ensure_ssl_certs(local_ip)

    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(certfile=cert_file, keyfile=key_file)

    app = web.Application()
    app.router.add_get("/", index_handler)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_get("/ping", ping_handler)
    app.router.add_route("OPTIONS", "/ping", ping_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, host="0.0.0.0", port=PORT, ssl_context=ssl_ctx).start()
    await web.TCPSite(runner, host="0.0.0.0", port=HTTP_PORT).start()

    udp_transport = None
    try:
        udp_transport, _ = await main_loop.create_datagram_endpoint(
            lambda: UdpDiscoveryProtocol(),
            local_addr=("0.0.0.0", HTTP_PORT),
        )
    except Exception:
        pass

    audio_engine.start()

    url = f"https://{local_ip}:{PORT}"

    print("\n" + "=" * 62)
    print(" [OK] SERVIDOR NEXOAUDIO ACTIVO Y ESCUCHANDO")
    print(f" >> URL directa: {url}")
    print(f" >> App Android -> IP autodetectable o manual: {', '.join(all_ips)}")
    print(" >> Escanea este código QR con la cámara de tu celular:")
    print("=" * 62 + "\n")

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)

    print("\n >> Presiona Ctrl + C para detener el servidor\n")

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        if udp_transport:
            try:
                udp_transport.close()
            except Exception:
                pass
        audio_engine.stop()
        await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[*] Servidor detenido por el usuario.")