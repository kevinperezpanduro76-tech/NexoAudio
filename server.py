import asyncio
import ipaddress
import json
import os
import queue
import socket
import ssl
import sys
import threading
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
CHUNK_FRAMES = 1024   # captura loopback (~21 ms)
MIC_FRAMES = 480      # salida a VB-Cable (~10 ms)
HEARTBEAT_SEC = 8     # ping al celular; si no responde, se cierra la sesión zombi
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTTP_PORT = 8080      # puerto sin TLS para la app Android (HTTP + WebSocket + UDP Discovery)
FROZEN = getattr(sys, "frozen", False)
APP_DIR = os.path.dirname(sys.executable) if FROZEN else BASE_DIR   # junto al .exe: cert.pem y key.pem persisten
RES_DIR = getattr(sys, "_MEIPASS", BASE_DIR)                        # recursos empaquetados (index.html)

mic_queue = queue.Queue(maxsize=8)
main_loop = None
active_ws = None   # única sesión activa
pc_queue = None    # cola de audio PC -> celular de la sesión activa


def get_all_local_ips():
    """Devuelve todas las direcciones IPv4 privadas activas de la PC (Wi-Fi, Ethernet, Zona portátil)."""
    ips = []
    for target in (("8.8.8.8", 80), ("192.168.137.1", 80), ("192.168.43.1", 80), ("192.168.1.1", 80)):
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
    return ips or ["127.0.0.1"]


def get_local_ip():
    """Obtiene la IP local principal de la tarjeta Wi-Fi/Ethernet/Hotspot activa."""
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
    """Verifica que el certificado exista, sea vigente y contenga la IP local actual en su SAN."""
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
    """Genera o actualiza el certificado SSL autofirmado si no existe o si cambió la IP local."""
    if os.path.exists(cert_path) and os.path.exists(key_path) and _cert_matches_ip(cert_path, local_ip):
        return cert_path, key_path

    print(f"[*] Generando certificado HTTPS local para {local_ip} (requerido por navegadores móviles para el micrófono)...")
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


def find_vbcable_devices(p: pyaudio.PyAudio):
    """Dispositivos de salida de VB-Cable, con los de la API WASAPI primero (menor latencia que MME)."""
    keywords = ("cable input", "vb-audio", "voicemeeter input", "voice meeter input")
    try:
        wasapi_idx = p.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]
    except Exception:
        wasapi_idx = None

    found = []
    for i in range(p.get_device_count()):
        dev = p.get_device_info_by_index(i)
        if dev.get("maxOutputChannels", 0) <= 0 or dev.get("isLoopbackDevice", False):
            continue
        if any(k in dev.get("name", "").lower() for k in keywords):
            found.append(dev)
    found.sort(key=lambda d: d.get("hostApi") != wasapi_idx)  # orden estable: WASAPI antes que el resto
    return found


def drain(q, empty_exc):
    while True:
        try:
            q.get_nowait()
        except empty_exc:
            return


def broadcast_pc_audio(data: bytes):
    """Envía el bloque de audio de la PC al celular activo sin acumular retraso."""
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


class AudioEngine:
    def __init__(self):
        self.p = pyaudio.PyAudio()
        self.loopback_stream = None
        self.mic_stream = None

        # 1. Captura de audio de PC (WASAPI Loopback)
        self.loopback_dev = self.p.get_default_wasapi_loopback()
        self.pc_rate = int(self.loopback_dev["defaultSampleRate"])
        self.pc_channels = int(self.loopback_dev["maxInputChannels"])

        # 2. Salida hacia Micrófono Virtual (VB-Cable)
        self.cable_dev = None
        self.mic_rate = 48000
        self.mic_channels = 1
        self.client_rate = 48000  # frecuencia del micrófono del celular activo

        # Estado continuo del resampler (solo lo usa el hilo escritor)
        self.resample_pos = 0.0
        self.prev_sample = 0

    def reset_resampler(self):
        self.resample_pos = 0.0
        self.prev_sample = 0

    def set_loopback_active(self, active: bool):
        """Activa o pausa la captura WASAPI según haya un cliente conectado."""
        if not self.loopback_stream:
            return
        try:
            if active and self.loopback_stream.is_stopped():
                self.loopback_stream.start_stream()
            elif not active and self.loopback_stream.is_active():
                self.loopback_stream.stop_stream()
        except Exception:
            pass

    def process_mic_chunk(self, raw_bytes: bytes, in_rate: int) -> bytes:
        """Convierte de la frecuencia del celular (ej. 48000Hz) a la de VB-Cable (ej. 44100Hz)."""
        out_rate = self.mic_rate
        out_channels = self.mic_channels

        if in_rate == out_rate and out_channels == 1:
            return raw_bytes

        samples = array("h")
        samples.frombytes(raw_bytes)
        n_in = len(samples)
        if n_in == 0:
            return b""

        if in_rate == out_rate and out_channels == 2:
            stereo = array("h", [0]) * (n_in * 2)
            stereo[0::2] = samples
            stereo[1::2] = samples
            return stereo.tobytes()

        # Resampling lineal continuo con preservación de muestra previa sin listas intermedias
        step = in_rate / out_rate
        pos = self.resample_pos
        prev = self.prev_sample
        out_arr = array("h")
        append = out_arr.append

        while pos < n_in:
            idx = int(pos)
            frac = pos - idx
            s0 = prev if idx == 0 else samples[idx - 1]
            s1 = samples[idx]
            val = int(s0 + frac * (s1 - s0))
            append(val)
            if out_channels == 2:
                append(val)
            pos += step

        self.resample_pos = pos - n_in
        self.prev_sample = samples[-1]
        return out_arr.tobytes()

    def _open_mic_stream(self):
        """Prueba cada dispositivo de VB-Cable (WASAPI primero), priorizando 48000Hz para evitar remuestreo."""
        for dev in find_vbcable_devices(self.p):
            default_rate = int(dev["defaultSampleRate"])
            candidate_rates = list(dict.fromkeys([48000, default_rate, 44100]))
            for rate in candidate_rates:
                for ch in (1, 2):
                    try:
                        stream = self.p.open(
                            format=pyaudio.paInt16,
                            channels=ch,
                            rate=rate,
                            output=True,
                            frames_per_buffer=MIC_FRAMES,
                            output_device_index=dev["index"],
                        )
                    except Exception:
                        continue
                    self.cable_dev, self.mic_rate, self.mic_channels, self.mic_stream = dev, rate, ch, stream
                    return True
        return False

    def start(self):
        def loopback_callback(in_data, frame_count, time_info, status):
            if pc_queue is not None and main_loop is not None:
                try:
                    main_loop.call_soon_threadsafe(broadcast_pc_audio, in_data)
                except RuntimeError:  # el loop ya se cerró
                    pass
            return (None, pyaudio.paContinue)

        self.loopback_stream = self.p.open(
            format=pyaudio.paInt16,
            channels=self.pc_channels,
            rate=self.pc_rate,
            input=True,
            start=False,  # inicia en pausa hasta que se conecte un cliente
            frames_per_buffer=CHUNK_FRAMES,
            input_device_index=self.loopback_dev["index"],
            stream_callback=loopback_callback,
        )
        print(f"[OK] Captura de PC lista (Loopback): {self.loopback_dev['name']} ({self.pc_rate}Hz, {self.pc_channels}ch)")

        if self._open_mic_stream():
            api = self.p.get_host_api_info_by_index(self.cable_dev["hostApi"])["name"]
            print(f"[OK] Micrófono Virtual conectado: {self.cable_dev['name']} [{api}] ({self.mic_rate}Hz, {self.mic_channels}ch)")
            if "WASAPI" not in api:
                print("[!] VB-Cable se abrió por una API distinta de WASAPI: la latencia del micrófono será mayor.")
            threading.Thread(target=self._mic_writer_worker, daemon=True).start()
        else:
            print("[!] AVISO: No se encontró o no se pudo abrir 'CABLE Input' (VB-Cable).")

    def _mic_writer_worker(self):
        last_err = None
        while True:
            data = mic_queue.get()
            if data is None:
                break
            try:
                out = self.process_mic_chunk(data, self.client_rate)
                if out:
                    self.mic_stream.write(out)
            except Exception as e:
                if repr(e) != last_err:  # un log por tipo de error, sin inundar la consola
                    last_err = repr(e)
                    print(f"[!] Error escribiendo al micrófono virtual: {e!r}")

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
        if self.mic_stream:
            try:
                self.mic_stream.stop_stream()
                self.mic_stream.close()
            except Exception:
                pass
        self.p.terminate()


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
    """Endpoint ligero con CORS y soporte de red privada para autodescubrimiento desde la app Android."""
    if request.method == "OPTIONS":
        return web.Response(status=204, headers=PING_HEADERS)
    sockname = request.transport.get_extra_info("sockname") if request.transport else None
    actual_ip = sockname[0] if sockname and isinstance(sockname, tuple) and sockname[0] != "0.0.0.0" else get_local_ip()
    return web.json_response(
        {"app": "nexoaudio", "ip": actual_ip},
        headers=PING_HEADERS,
    )


async def websocket_handler(request):
    global active_ws, pc_queue

    ws = web.WebSocketResponse(heartbeat=HEARTBEAT_SEC, max_msg_size=1 << 16)
    await ws.prepare(request)

    q = asyncio.Queue(maxsize=8)

    # Sesión única: la conexión nueva reemplaza a la anterior
    old, active_ws, pc_queue = active_ws, ws, q
    if old is not None and not old.closed:
        print("[*] Nueva conexión: reemplazando la sesión anterior")
        try:
            await asyncio.wait_for(old.close(code=WSCloseCode.GOING_AWAY, message=b"replaced"), 2)
        except Exception:
            pass

    drain(mic_queue, queue.Empty)
    audio_engine.client_rate = 48000
    audio_engine.reset_resampler()
    audio_engine.set_loopback_active(True)
    print(f"[+] Celular conectado desde {request.remote}")

    await ws.send_str(
        json.dumps(
            {
                "type": "config",
                "pc_rate": audio_engine.pc_rate,
                "pc_channels": audio_engine.pc_channels,
                "mic_rate": audio_engine.mic_rate,
                "mic_channels": audio_engine.mic_channels,
                "vbcable_active": audio_engine.mic_stream is not None,
            }
        )
    )
    drain(q, asyncio.QueueEmpty)  # descarta lo acumulado mientras se reemplazaba la sesión previa

    async def send_pc_audio_loop():
        try:
            while not ws.closed:
                await ws.send_bytes(await q.get())
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
                        if 8000 <= rate <= 192000:  # evita step = 0 (bucle infinito) y valores absurdos
                            audio_engine.client_rate = rate
                            audio_engine.reset_resampler()
                            print(f"[*] Micrófono del celular a {rate}Hz -> Salida VB-Cable a {audio_engine.mic_rate}Hz")
                except Exception:
                    pass

            elif msg.type == WSMsgType.BINARY and audio_engine.mic_stream is not None:
                raw = msg.data[: len(msg.data) & ~1]  # int16 = 2 bytes por muestra
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
            audio_engine.set_loopback_active(False)
        print(f"[-] Celular desconectado ({request.remote})")

    return ws


async def main():
    global main_loop
    main_loop = asyncio.get_running_loop()

    # Asegurar salida UTF-8 en consola de Windows para dibujar los bloques del QR
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
    site = web.TCPSite(runner, host="0.0.0.0", port=PORT, ssl_context=ssl_ctx)
    await site.start()
    await web.TCPSite(runner, host="0.0.0.0", port=HTTP_PORT).start()  # sin TLS, para la app Android

    # Servidor UDP en puerto 8080 para autodescubrimiento instantáneo por Broadcast desde Android
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

    # Generar e imprimir el código QR directamente en la terminal
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
