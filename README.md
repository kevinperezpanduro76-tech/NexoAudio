# NexoAudio

**NexoAudio** es un puente de audio bidireccional en tiempo real y de baja latencia entre tu PC (Windows) y tu celular (Android o navegador móvil) a través de tu red local Wi-Fi o zona portátil (*mobile hotspot*).

Convierte tu teléfono en unos audífonos inalámbricos para escuchar todo lo que suena en tu PC y, al mismo tiempo, usa el micrófono de tu celular como micrófono inalámbrico para Discord, juegos, llamadas o streaming.

## Características principales

* **Audio de PC a Celular:** Captura el sonido del escritorio mediante **WASAPI Loopback** (con soporte de mezcla automática de 5.1 a estéreo) y lo reproduce en el móvil sin retraso perceptible.
* **Micrófono de Celular a PC:** Transmite tu voz hacia Windows a través de **VB-Cable**, priorizando frecuencias de 48 kHz en WASAPI para evitar remuestreos innecesarios.
* ** Motor de latencia ultrabaja:** Construido sobre un `AudioWorklet` personalizado con *ring buffer*, colchón de *jitter* de 50 ms, interpolación lineal y ajuste dinámico de velocidad (±1 %) para compensar la deriva de relojes sin cortes ni chasquidos.
* ** Controles en vivo:** Activa o silencia el altavoz y el micrófono al instante, o alterna entre **audio en crudo** y **cancelación de eco (Anti-eco)** en caliente sin desconectar la sesión.
* ** Doble vía de conexión:**
  * **Sin instalar nada (Web):** Escanea el código QR de la consola para abrir la interfaz web por HTTPS (puerto 8443).
  * **App Android nativa:** Conecta mediante HTTP (puerto 8080) con **autodescubrimiento de IP** en la red local.
* ** Pantalla activa:** Integración con `Wake Lock API` y recuperación automática de sesión al volver a la aplicación.

## Guía de uso rápido

### 1. En tu PC (Windows 10/11)
1. *(Opcional pero recomendado)* Si quieres usar el micrófono de tu celular en la PC, descarga e instala **[VB-Cable](https://vb-audio.com/Cable/)** y reinicia tu PC.
2. Ejecuta `NexoAudio.exe` (descargado desde **Actions / Releases**) o inicia el servidor con `python server.py`.
3. Si aparece una alerta del **Firewall de Windows**, marca las casillas de **Redes privadas** y permite el acceso.

### 2. En tu Celular

#### Opción A: Desde la App de Android (APK)
1. Instala `NexoAudio.apk` en tu teléfono (asegúrate de estar en la misma red Wi-Fi que tu PC).
2. Al abrir la app, buscará automáticamente la IP de tu laptop en la red local. Si no la detecta, escríbela manualmente o toca el botón ****.
3. Toca **CONECTAR** y acepta el permiso de micrófono.

#### Opción B: Desde el navegador (Chrome / Safari / Edge)
1. Escanea el **código QR** que aparece en la consola de tu PC.
2. En el aviso del certificado autofirmado (*"La conexión no es privada"*), toca en **Configuración avanzada** -> **Continuar a 192.168.x.x (no seguro)**.
3. Toca **CONECTAR** y permite el acceso al micrófono.

### 3. Configurar el micrófono en Discord, Zoom o Juegos
1. Abre la configuración de sonido de tu programa o de Windows.
2. En **Dispositivo de entrada (Micrófono)**, selecciona **`CABLE Output (VB-Audio Virtual Cable)`**.

## 🛠️ Compilación desde código fuente

### Ejecutar en desarrollo
```bash
pip install -r requirements.txt
python server.py
```

### Compilar ejecutable de Windows (.exe)
```cmd
build.bat
```

### Compilar aplicación Android (.apk)
```bash
npm install
npm run sync
npm run open:android
```

## 💜 Apoya el proyecto
* **[Apoyar en Patreon (Kaell456)](https://patreon.com/Kaell456)**
