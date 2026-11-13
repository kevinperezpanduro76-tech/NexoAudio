# NexoAudio
[English](#english) | [Español](#español)

---

<a name="english"></a>
## English

**NexoAudio** is a real-time, low-latency bidirectional audio bridge between your Windows PC and your phone (Android app or mobile browser) over a local Wi-Fi network or mobile hotspot.

Turn your phone into a wireless speaker/headset to listen to your PC audio and, simultaneously, use your phone's microphone as a wireless microphone for Discord, games, calls, or streaming.

### Key Features

* **PC to Phone Audio:** Captures desktop sound via **WASAPI Loopback** (including automatic 5.1 surround to stereo downmixing) and streams it to your phone in real time.
* **Phone to PC Microphone:** Routes your voice into Windows through **VB-Cable**, prioritizing 48 kHz over WASAPI to avoid unnecessary resampling.
* **Ultra-Low Latency Engine:** Powered by a custom `AudioWorklet` with a ring buffer, a 50 ms jitter cushion, linear interpolation, and dynamic clock drift compensation (±1%) for glitch-free playback.
* **Live Controls:** Mute or unmute speaker and microphone instantly, or toggle between **raw audio** and **echo cancellation (Anti-echo)** on the fly without dropping the session.
* **Dual Connection Modes:**
  * **Mobile Browser (No installation required):** Scan the console QR code to connect over HTTPS (port 8443).
  * **Native Android App:** Connects over HTTP (port 8080) with **automatic local IP discovery**.
* **Keep Screen Awake:** Integrated with the `Wake Lock API` and automatic session recovery when returning to the foreground.

### Quick Start Guide

#### 1. On your PC (Windows 10/11)
1. *(Optional, required for microphone forwarding)* Download and install **[VB-Cable](https://vb-audio.com/Cable/)**, then restart your PC.
2. Run `NexoAudio.exe` (from **Actions / Releases**) or start the server from source using `python server.py`.
3. If prompted by **Windows Defender Firewall**, allow access on **Private networks**.

#### 2. On your Phone

##### Option A: Android App (APK)
1. Install `NexoAudio.apk` on your phone (make sure both devices are on the same Wi-Fi network or hotspot).
2. Open the app. It will automatically scan the local network for your PC's IP address, or you can enter it manually.
3. Tap **CONECTAR** and grant microphone permissions.

##### Option B: Mobile Browser (Chrome / Safari / Edge)
1. Scan the **QR code** displayed in the PC terminal.
2. On the self-signed certificate warning (*"Your connection is not private"*), tap **Advanced** -> **Proceed to 192.168.x.x (unsafe)**.
3. Tap **CONECTAR** and allow microphone access.

#### 3. Using the Phone Microphone in Discord, Zoom, or Games
1. Open the audio settings of your application or Windows Sound Settings.
2. Under **Input Device (Microphone)**, select **`CABLE Output (VB-Audio Virtual Cable)`**.

### Building from Source

#### Run in Development Mode
```bash
pip install -r requirements.txt
python server.py
```

#### Build Windows Executable (.exe)
```cmd
build.bat
```

#### Build Android APK (Capacitor)
```bash
npm install
npm run sync
npm run open:android
```

### Troubleshooting

* **Cannot connect or no audio on phone:** Ensure both devices share the same Wi-Fi network or mobile hotspot, and verify that TCP ports `8443` and `8080` are allowed through the Windows Firewall.
* **Browser rejects certificate after switching Wi-Fi networks:** Restart `NexoAudio.exe`; the server automatically detects local IP changes and regenerates the SSL certificate.
* **Echo when speaking:** Use headphones on your phone or enable the **Anti-eco: ON** button in the app interface.

### Support the Project
* **[Support on Patreon (Kaell456)](https://patreon.com/Kaell456)**

---

<a name="español"></a>
## Español

**NexoAudio** es un puente de audio bidireccional en tiempo real y de baja latencia entre tu PC (Windows) y tu celular (app Android o navegador móvil) a través de tu red local Wi-Fi o zona portátil (*mobile hotspot*).

Convierte tu teléfono en unos audífonos o altavoces inalámbricos para escuchar todo lo que suena en tu PC y, al mismo tiempo, usa el micrófono de tu celular como micrófono inalámbrico para Discord, juegos, llamadas o streaming.

### Características Principales

* **Audio de PC a Celular:** Captura el sonido del escritorio mediante **WASAPI Loopback** (con soporte de mezcla automática de 5.1 a estéreo) y lo reproduce en el móvil sin retraso perceptible.
* **Micrófono de Celular a PC:** Transmite tu voz hacia Windows a través de **VB-Cable**, priorizando frecuencias de 48 kHz en WASAPI para evitar remuestreos innecesarios.
* **Motor de Latencia Ultrabaja:** Construido sobre un `AudioWorklet` personalizado con *ring buffer*, colchón de *jitter* de 50 ms, interpolación lineal y ajuste dinámico de velocidad (±1 %) para compensar la deriva de relojes sin cortes ni chasquidos.
* **Controles en Vivo:** Activa o silencia el altavoz y el micrófono al instante, o alterna entre **audio en crudo** y **cancelación de eco (Anti-eco)** en caliente sin desconectar la sesión.
* **Doble Vía de Conexión:**
  * **Navegador Móvil (sin instalar nada):** Escanea el código QR de la consola para abrir la interfaz web por HTTPS (puerto 8443).
  * **App Android Nativa:** Conecta mediante HTTP (puerto 8080) con **autodescubrimiento de IP** en la red local.
* **Pantalla Activa:** Integración con `Wake Lock API` y recuperación automática de sesión al volver a la aplicación.

### Guía de Uso Rápido

#### 1. En tu PC (Windows 10/11)
1. *(Opcional, requerido para usar el micrófono)* Descarga e instala **[VB-Cable](https://vb-audio.com/Cable/)** y reinicia tu PC.
2. Ejecuta `NexoAudio.exe` (descargado desde **Actions / Releases**) o inicia el servidor con `python server.py`.
3. Si aparece una alerta del **Firewall de Windows**, marca la casilla de **Redes privadas** y permite el acceso.

#### 2. En tu Celular

##### Opción A: Desde la App de Android (APK)
1. Instala `NexoAudio.apk` en tu teléfono (asegúrate de estar en la misma red Wi-Fi o zona portátil que tu PC).
2. Al abrir la app, buscará automáticamente la IP de tu laptop en la red local. Si no la detecta, escríbela manualmente.
3. Toca **CONECTAR** y acepta el permiso de micrófono.

##### Opción B: Desde el Navegador (Chrome / Safari / Edge)
1. Escanea el **código QR** que aparece en la consola de tu PC.
2. En el aviso del certificado autofirmado (*"La conexión no es privada"*), toca en **Configuración avanzada** -> **Continuar a 192.168.x.x (no seguro)**.
3. Toca **CONECTAR** y permite el acceso al micrófono.

#### 3. Configurar el Micrófono en Discord, Zoom o Juegos
1. Abre la configuración de sonido de tu programa o de Windows.
2. En **Dispositivo de entrada (Micrófono)**, selecciona **`CABLE Output (VB-Audio Virtual Cable)`**.

### Compilación desde Código Fuente

#### Ejecutar en Modo Desarrollo
```bash
pip install -r requirements.txt
python server.py
```

#### Compilar Ejecutable de Windows (.exe)
```cmd
build.bat
```

#### Compilar Aplicación Android (.apk)
```bash
npm install
npm run sync
npm run open:android
```

### Solución de Problemas Comunes

* **No se escucha nada o no conecta desde el celular:** Verifica que ambos dispositivos estén en la misma red Wi-Fi o zona portátil y que los puertos TCP `8443` y `8080` estén permitidos en el Firewall de Windows.
* **Cambié de red Wi-Fi y el navegador rechaza el certificado:** Reinicia `NexoAudio.exe`; el servidor detectará el cambio de IP local y regenerará el certificado SSL automáticamente.
* **Se escucha eco cuando hablo:** Usa audífonos en el celular o activa el botón **Anti-eco: ON** en la interfaz de la aplicación.

### Apoya el Proyecto
* **[Apoyar en Patreon (Kaell456)](https://patreon.com/Kaell456)**

---

## License / Licencia

MIT License.*
