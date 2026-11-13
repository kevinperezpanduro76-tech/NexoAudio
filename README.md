# NexoAudio

[English](#english) | [Español](#español)

---

<a name="english"></a>
## English

**NexoAudio** is a real-time, ultra-low-latency bidirectional audio bridge between your Windows PC/laptop and your phone (Android app or mobile browser) over a local Wi-Fi network or mobile hotspot.

Turn your phone into a wireless speaker/headset to listen to your PC audio and, simultaneously, use your phone's microphone as a wireless microphone for Discord, games, calls, or streaming.

### Downloads (Ready to Use)

You do not need to compile the code to use NexoAudio. Download the latest pre-built installers directly from the **[GitHub Releases page](https://github.com/kevinperezpanduro76-tech/NexoAudio/releases/latest)**:

* **Windows PC / Laptop (`NexoAudio.exe`):** Standalone server executable (no Python installation required).
* **Android Phone (`NexoAudio.apk`):** Native Android application with instant IP discovery and automatic connection.

> **IMPORTANT REQUIREMENT:** To use the Android APK (or the mobile browser), **`NexoAudio.exe` MUST be open and running in the terminal window on your PC/laptop**. The PC program acts as the audio server that captures Windows sound and receives your microphone audio.

### Key Features

* **PC to Phone Audio:** Captures desktop sound via **WASAPI Loopback** in `10 ms` frames (`480` samples) with `TCP_NODELAY` (including automatic 5.1 surround to stereo downmixing) and streams it to your phone in real time.
* **Phone to PC Microphone:** Routes your voice into Windows through **VB-Cable**, prioritizing `48 kHz` over WASAPI to avoid unnecessary resampling.
* **Anti-Click / Glitch-Free Audio Engine:** Powered by a custom `AudioWorklet` with a ring buffer, a `75 ms` jitter cushion, continuous crossfade smoothing (eliminating audio pops/claps on network micro-drops), and a deadband clock-drift filter (`+/- 0.5%`).
* **Per-Device Sample Rate (`Hz`) Adaptation:** Automatically detects the native hardware sample rate of each phone (`48000 Hz`, `44100 Hz`, etc.) and adapts the stream in real time to avoid double resampling by Android.
* **Zero-Touch Auto-Connect (Android APK):**
  * **Instant Hybrid Discovery:** Finds your laptop in milliseconds using native **UDP Broadcast** (port `8080`), native Android network interface inspection, Windows/Android Hotspot gateway detection (`192.168.137.1`, `192.168.43.1`), and smart subnet scanning.
  * **Automatic Connection & Background Retry:** Connects automatically as soon as your PC server is detected. If you open the APK before starting `NexoAudio.exe` on your PC, the app waits and retries every 3.5 seconds until you open the `.exe`.
* **Live Controls:** Mute or unmute speaker and microphone instantly, or toggle between **raw audio** and **echo cancellation (Anti-echo)** on the fly without dropping the session.
* **Keep Screen Awake:** Integrated with the `Wake Lock API`, native Android WebView media permissions, and automatic session recovery.

### Quick Start Guide

#### 1. On your PC or Laptop (Windows 10/11) — *Must Stay Open*
1. *(Optional, required for microphone forwarding)* Download and install **[VB-Cable](https://vb-audio.com/Cable/)**, then restart your PC.
2. Download and run **`NexoAudio.exe`** from **[Releases](https://github.com/kevinperezpanduro76-tech/NexoAudio/releases/latest)** (or start the server from source using `python server.py`).
3. **Keep the black terminal window open** while using NexoAudio (you can minimize it, but do not close it).
4. If prompted by **Windows Defender Firewall**, check **Private networks** (and **Public networks** if you use a mobile hotspot) and allow access.

> **Tip (Auto-start with Windows):** If you don't want to open `NexoAudio.exe` manually every time, press `Win + R` on your PC, type `shell:startup`, press **Enter**, and paste a **shortcut** to `NexoAudio.exe` inside that folder.

#### 2. On your Phone

##### Option A: Android App (APK) — *Recommended*
1. Download and install **`NexoAudio.apk`** from **[Releases](https://github.com/kevinperezpanduro76-tech/NexoAudio/releases/latest)** on your phone (make sure both your phone and laptop are on the same Wi-Fi network or mobile hotspot).
2. Make sure **`NexoAudio.exe` is open on your laptop**, then open the **NexoAudio** app on your phone.
3. **It will detect your PC's IP and connect automatically!** (On the first run, accept the microphone permission prompt).

##### Option B: Mobile Browser (Chrome / Safari / Edge — No installation required)
1. With **`NexoAudio.exe` open on your PC**, scan the **QR code** displayed in the PC terminal window.
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
The `android/` project is generated with `npx cap add android`, and then the files in `android-overlay/` (`AndroidManifest.xml` and `MainActivity.java` with the native UDP/subnet discovery bridge) are copied on top of it.

**Option 1: GitHub Actions (easiest, nothing to install)**
1. Go to the **Actions** tab of the repository.
2. Open the latest run of **Build NexoAudio (Windows EXE + Android APK)**, or start a new one with **Run workflow**.
3. When the jobs finish, download `NexoAudio-Android-APK` and `NexoAudio-Windows-EXE` from the **Artifacts** section.

**Option 2: Build locally**

Requirements: Node.js 18+ (20 recommended), JDK 17, and the Android SDK (installed with Android Studio).

```cmd
npm install
npm run copy:web
npx cap add android
xcopy android-overlay android /E /Y /I
npx cap sync android
cd android
gradlew assembleDebug
```

On Linux/macOS, replace the `xcopy` line with `cp -r android-overlay/* android/` and use `./gradlew assembleDebug`.

The APK will be at:
```text
android/app/build/outputs/apk/debug/app-debug.apk
```

### Troubleshooting

* **The APK stays on *"Waiting for your laptop on the network..."*:**
  1. Verify that **`NexoAudio.exe` is open and running** on your PC/laptop.
  2. Ensure both devices are connected to the same Wi-Fi network or mobile hotspot.
  3. Verify that TCP/UDP port `8080` and TCP port `8443` are allowed through the Windows Firewall.
* **Audio cuts out after locking the phone screen for several minutes:** On your Android phone, long-press the **NexoAudio** app icon -> **App info** -> **Battery** -> select **Unrestricted** so Android does not throttle the Wi-Fi or CPU while the screen is off.
* **Browser rejects certificate after switching Wi-Fi networks:** Restart `NexoAudio.exe`; the server automatically detects local IP changes across all network adapters and regenerates the SSL certificate.
* **Echo when speaking:** Use headphones on your phone or enable the **Anti-eco: ON** button in the app interface.

### Support the Project
* **[Support on Patreon (Kaell456)](https://patreon.com/Kaell456)**

---

<a name="español"></a>
## Español

**NexoAudio** es un puente de audio bidireccional en tiempo real y de latencia ultrabaja entre tu PC o laptop (Windows) y tu celular (app Android o navegador móvil) a través de tu red local Wi-Fi o zona portátil (*mobile hotspot*).

Convierte tu teléfono en unos audífonos o altavoces inalámbricos para escuchar todo lo que suena en tu PC y, al mismo tiempo, usa el micrófono de tu celular como micrófono inalámbrico para Discord, juegos, llamadas o streaming.

### Descargas (Listo para Usar)

No necesitas compilar el código para usar NexoAudio. Descarga los instaladores listos para abrir directamente desde la sección **[Releases de GitHub](https://github.com/kevinperezpanduro76-tech/NexoAudio/releases/latest)**:

* **PC / Laptop Windows (`NexoAudio.exe`):** Servidor ejecutable portátil (no requiere instalar Python).
* **Celular Android (`NexoAudio.apk`):** Aplicación nativa para Android con detección instantánea de IP y conexión automática.

> **REQUISITO IMPORTANTE:** Para que la APK de Android (o el navegador móvil) funcione y se conecte, **debes tener abierto `NexoAudio.exe` (la ventana de consola/terminal) en tu PC o laptop**. El programa de la PC es el servidor que captura el audio de Windows y recibe la señal de tu micrófono.

### Características Principales

* **Audio de PC a Celular:** Captura el sonido del escritorio mediante **WASAPI Loopback** en bloques de `10 ms` (`480` muestras) con `TCP_NODELAY` (con soporte de mezcla automática de 5.1 a estéreo) y lo reproduce en el móvil en tiempo real.
* **Micrófono de Celular a PC:** Transmite tu voz hacia Windows a través de **VB-Cable**, priorizando frecuencias de `48 kHz` en WASAPI para evitar remuestreos innecesarios.
* **Motor de Audio Anti-Chasquidos (*Anti-Click*):** Construido sobre un `AudioWorklet` personalizado con *ring buffer*, colchón anti-jitter de `75 ms`, fundido cruzado continuo (*crossfade*) que elimina chasquidos o *"claps"* ante micro-cortes de Wi-Fi, y filtro con zona muerta (`+/- 0.5%`) para compensar la deriva de relojes.
* **Adaptación de Frecuencia (`Hz`) por Dispositivo:** Detecta automáticamente los `Hz` nativos de hardware de cada celular (`48000 Hz`, `44100 Hz`, etc.) y adapta el flujo de audio en tiempo real para evitar que Android realice un doble remuestreo.
* **Autoconexión Inteligente en la APK:**
  * **Descubrimiento Híbrido Instantáneo:** Encuentra la IP de tu laptop en milisegundos mediante **Broadcast UDP nativo** (puerto `8080`), lectura nativa de las subredes del teléfono, detección directa de Zona Portátil de Windows/Android (`192.168.137.1`, `192.168.43.1`) y escaneo con concurrencia controlada.
  * **Conexión Automática y Reintento en Segundo Plano:** Se conecta sola en cuanto detecta el servidor de tu PC. Si abres primero la APK en el celular, quedará en espera buscando cada 3.5 segundos y se conectará automáticamente en cuanto abras `NexoAudio.exe` en tu laptop.
* **Controles en Vivo:** Activa o silencia el altavoz y el micrófono al instante, o alterna entre **audio en crudo** y **cancelación de eco (Anti-eco)** en caliente sin desconectar la sesión.
* **Pantalla Activa:** Integración con `Wake Lock API`, permisos nativos en el WebView de Android y recuperación automática de sesión.

### Guía de Uso Rápido

#### 1. En tu PC o Laptop (Windows 10/11) — *Debe permanecer abierto*
1. *(Opcional, requerido para usar el micrófono)* Descarga e instala **[VB-Cable](https://vb-audio.com/Cable/)** y reinicia tu PC.
2. Descarga y ejecuta **`NexoAudio.exe`** desde **[Releases](https://github.com/kevinperezpanduro76-tech/NexoAudio/releases/latest)** (o inicia el servidor desde el código fuente con `python server.py`).
3. **Mantén abierta la ventana negra de la consola (terminal)** mientras uses la aplicación (puedes minimizarla, pero no la cierres).
4. Si aparece una alerta del **Firewall de Windows**, marca las casillas de **Redes privadas** (y **Redes públicas** si conectas por Zona Portátil / Hotspot) y permite el acceso.

> **Consejo (Iniciar automáticamente con Windows):** Si quieres que el servidor de la PC se abra solo al encender tu laptop, presiona `Windows + R`, escribe `shell:startup`, presiona **Enter** y pega ahí dentro un **acceso directo** de `NexoAudio.exe`.

#### 2. En tu Celular

##### Opción A: Desde la App de Android (APK) — *Recomendado*
1. Descarga e instala **`NexoAudio.apk`** desde **[Releases](https://github.com/kevinperezpanduro76-tech/NexoAudio/releases/latest)** en tu teléfono (asegúrate de estar en la misma red Wi-Fi o zona portátil que tu laptop).
2. Con **`NexoAudio.exe` abierto en tu PC**, abre la aplicación **NexoAudio** en tu celular.
3. **¡La app detectará la IP de tu laptop y se conectará sola automáticamente!** (La primera vez que la abras, acepta el permiso de micrófono).

##### Opción B: Desde el Navegador (Chrome / Safari / Edge — Sin instalar APK)
1. Con **`NexoAudio.exe` abierto en tu PC**, escanea el **código QR** que aparece en la ventana de consola de tu PC.
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
El proyecto `android/` se genera con `npx cap add android` y luego se copian encima los archivos de `android-overlay/` (`AndroidManifest.xml` y `MainActivity.java` con el puente nativo de descubrimiento UDP y lectura de subred).

**Opción 1: GitHub Actions (la más fácil, sin instalar nada)**
1. Entra a la pestaña **Actions** del repositorio.
2. Abre la última ejecución de **Build NexoAudio (Windows EXE + Android APK)**, o inicia una nueva con **Run workflow**.
3. Cuando terminen los trabajos, descarga los artefactos `NexoAudio-Android-APK` y `NexoAudio-Windows-EXE` en la parte inferior.

**Opción 2: Compilar en tu PC**

Requisitos: Node.js 18+ (recomendado 20), JDK 17 y el Android SDK (se instala con Android Studio).

```cmd
npm install
npm run copy:web
npx cap add android
xcopy android-overlay android /E /Y /I
npx cap sync android
cd android
gradlew assembleDebug
```

En Linux/macOS, reemplaza la línea de `xcopy` por `cp -r android-overlay/* android/` y usa `./gradlew assembleDebug`.

El APK quedará en:
```text
android/app/build/outputs/apk/debug/app-debug.apk
```

### Solución de Problemas Comunes

* **La APK se queda en *"Esperando a tu laptop en la red..."*:**
  1. Verifica que **`NexoAudio.exe` esté abierto y ejecutándose** en tu PC o laptop.
  2. Comprueba que ambos dispositivos estén en la misma red Wi-Fi o zona portátil (*hotspot*).
  3. Verifica que el puerto TCP/UDP `8080` y el puerto TCP `8443` estén permitidos en el Firewall de Windows.
* **El audio se entrecorta después de varios minutos con la pantalla del celular apagada:** Mantén presionado el ícono de **NexoAudio** en tu celular -> **Información de la aplicación** -> **Batería** -> selecciona **Sin restricciones** para evitar que el ahorro de batería de Android limite el Wi-Fi.
* **Cambié de red Wi-Fi y el navegador rechaza el certificado:** Reinicia `NexoAudio.exe`; el servidor detectará el cambio de IP en tus tarjetas de red y regenerará el certificado SSL automáticamente.
* **Se escucha eco cuando hablo:** Usa audífonos en el celular o activa el botón **Anti-eco: ON** en la interfaz de la aplicación.

### Apoya el Proyecto
* **[Apoyar en Patreon (Kaell456)](https://patreon.com/Kaell456)**

---

## License / Licencia

MIT License.