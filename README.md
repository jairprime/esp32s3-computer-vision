# Detector de Personas — Laboratorio de Competencias Digitales 3

Sistema de visión por computador que vigila el Laboratorio de Competencias Digitales 3 de la Universidad CESMAG y avisa por **Telegram** cuando el aula queda vacía, para saber cuándo ir a cerrarla sin revisar las cámaras de seguridad. Una placa **ESP32-S3** con cámara toma fotos del aula, un programa en **Python** cuenta las personas con el modelo **YOLO11n** y, cuando el aula lleva varios minutos sin nadie, envía al celular un mensaje con la foto del aula vacía.

## Stack

| Capa         | Tecnología                                                                  |
| ------------ | --------------------------------------------------------------------------- |
| Hardware     | ESP32-S3-WROOM N16R8 (16 MB flash, 8 MB PSRAM octal), cámara OV2640         |
| Firmware     | Arduino (C++), core ESP32 de Espressif, `esp_camera`, `WebServer`, `HTTPClient` |
| Visión       | Python 3.12, Ultralytics YOLO11n, PyTorch (CPU), OpenCV                     |
| Avisos       | API de bots de Telegram (`requests`)                                        |
| Red          | Punto de acceso propio `LAB8-CAMARA`; túnel con ngrok o Cloudflare Tunnel   |
| Herramientas | `arduino-cli`, `nmcli`                                                      |

## Características

- **Conteo de personas** con YOLO11n cada 2 segundos; la última foto analizada se guarda con los recuadros en `deteccion.jpg`.
- **Aviso de aula vacía**: un mensaje con la foto cuando el aula lleva N minutos seguidos sin nadie (5 por defecto), con el máximo de personas que hubo.
- **Aviso de cámara caída**: si no llegan fotos durante 5 minutos (se apagó la placa o se fue la luz), avisa, y vuelve a avisar cuando se recupera.
- **Dos modos de funcionamiento**:
  - **Pedir**: el PC, conectado a la red `LAB8-CAMARA`, le pide las fotos a la placa.
  - **Recibir**: la placa, lejos en el laboratorio, envía las fotos por internet a través de un túnel con dirección fija.
- **Página web en la placa** para ver la cámara en vivo, apuntarla y revisar su estado.
- **Autodiagnóstico de red**: al encender, la placa comprueba si puede salir a internet (DNS, HTTP, HTTPS y subida de 30 KB de prueba, sin enviar fotos del aula a terceros).
- **Robustez**: descarta fotos dañadas, se reinicia sola si la cámara falla al arrancar y sigue funcionando aunque Telegram no responda.
- **Seguridad**: las fotos llevan una clave en la cabecera `X-Clave` (comparada en tiempo constante); el receptor solo escucha en `127.0.0.1`, rechaza envíos de más de 2 MB y cierra las conexiones que no envían nada en 10 s; los errores de Telegram no muestran el token.

## Cómo funciona

```
Cargador ──► ESP32-S3 + cámara ──WiFi "LAB8-CAMARA"──► PC: contador.py ──internet──► 📱 Telegram
             (192.168.4.1)                             (YOLO + VigilanteAula)
```

La clase `VigilanteAula` (en `contador.py`) decide cuándo avisar:

```
        2 fotos seguidas con gente              N minutos seguidos sin nadie
LIBRE  ─────────────────────────────►  OCUPADA  ─────────────────────────►  LIBRE
                                          │  aparece alguien:                 │
                                          └─ se reinicia la cuenta            └─► 📱 aviso
```

| Regla                                                      | Para qué sirve                                                       |
| ---------------------------------------------------------- | -------------------------------------------------------------------- |
| El aula pasa a ocupada solo con 2 fotos seguidas con gente | Un error del modelo en una sola foto no cuenta                       |
| Avisa solo tras N minutos seguidos en 0                    | Alguien tapado o agachado no dispara un aviso falso                  |
| Si el aula nunca tuvo gente, no avisa                      | No llegan mensajes por la mañana antes de abrir                      |
| Un solo aviso por cada vez que se vacía                    | No repite mensajes mientras siga vacía                               |
| Las fotos dañadas se descartan                             | Con una foto vacía, YOLO analiza sus imágenes de ejemplo y cuenta personas inexistentes |

**¿Por qué la placa crea su propia red?** La red ADMON de la universidad aísla a los equipos conectados por WiFi: el PC no puede pedirle fotos a la placa a través de ella. Por eso la placa funciona en modo `AP_STA`: crea la red `LAB8-CAMARA` para el PC y, al mismo tiempo, se conecta a ADMON para salir a internet. El PC mantiene su internet por el cable de red.

## Estructura

```
esp32s3-computer-vision/
├── esp32s3-computer-vision.ino  # Firmware: cámara, red LAB8-CAMARA, ADMON, servidor web y envío de fotos
├── credenciales.ejemplo.h       # Plantilla de credenciales.h
├── contador.py                  # Conteo con YOLO, VigilanteAula y avisos
├── aviso_telegram.py            # Envío de mensajes y fotos al bot
├── receptor.py                  # Recibe las fotos de la placa y abre el túnel (ngrok o Cloudflare)
├── receptor.ejemplo.json        # Plantilla de receptor.json
├── telegram.ejemplo.json        # Plantilla de telegram.json
├── requirements.txt             # Dependencias (incluye el índice de PyTorch para CPU)
└── .gitignore                   # Deja fuera de git los datos privados, venv/, el modelo y las fotos
```

## Requisitos

- Python 3.12
- [`arduino-cli`](https://arduino.github.io/arduino-cli/) con el core de ESP32: `arduino-cli core install esp32:esp32`
- Placa ESP32-S3 N16R8 con cámara OV2640 y un cargador de 5 V y al menos 1 A
- Una cuenta de Telegram para crear el bot
- Para el modo recibir: [ngrok](https://ngrok.com) (dirección fija, recomendado) o [`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) (dirección temporal)
- Linux con NetworkManager (`nmcli`) para cambiar de red WiFi desde la terminal

### Hardware

| Componente   | Detalle                                                                  |
| ------------ | ------------------------------------------------------------------------ |
| Placa        | ESP32-S3-WROOM N16R8                                                     |
| Cámara       | OV2640 por cable flex, con el mapa de pines de `CAMERA_MODEL_ESP32S3_EYE` |
| USB-serie    | CH343 (`1a86:55d3`); aparece como `/dev/ttyACM0`                         |
| Fotos        | JPEG de 640x480 (VGA), calidad 12, unos 30 KB cada una                   |

## Instalación

```bash
git clone https://github.com/jairprime/esp32s3-computer-vision
cd esp32s3-computer-vision
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Archivos privados a partir de las plantillas (luego complétalos, ver Configuración)
cp credenciales.ejemplo.h credenciales.h
cp telegram.ejemplo.json telegram.json
cp receptor.ejemplo.json receptor.json
```

El modelo `yolo11n.pt` (~5 MB) no está en el repositorio: se descarga solo la primera vez que corre `contador.py`.

> `requirements.txt` ya incluye el índice de PyTorch para CPU, así que no descarga las versiones con soporte de tarjeta gráfica (varios GB).

Carga el firmware en la placa (conectada por USB), después de crear `credenciales.h` (ver [Configuración](#configuración)):

```bash
FQBN=esp32:esp32:esp32s3:PSRAM=opi,FlashSize=16M,PartitionScheme=huge_app
arduino-cli compile -b $FQBN .
arduino-cli upload  -b $FQBN -p /dev/ttyACM0 .
```

> El sketch se llama igual que la carpeta (`esp32s3-computer-vision.ino`) porque Arduino lo exige. Si la carga falla, mantén pulsado **BOOT**, pulsa y suelta **RST**, y vuelve a intentarlo.

## Configuración

Hay tres archivos con datos privados. **Nunca los subas a un repositorio**: ya están en `.gitignore`. Se crean copiando las plantillas `*.ejemplo.*` (ver [Instalación](#instalación)), que sí están en git y no contienen datos reales.

| Archivo privado  | Plantilla               | Lo usa                         |
| ---------------- | ----------------------- | ------------------------------ |
| `credenciales.h` | `credenciales.ejemplo.h` | El firmware de la placa        |
| `receptor.json`  | `receptor.ejemplo.json`  | `contador.py --recibir`        |
| `telegram.json`  | `telegram.ejemplo.json`  | `contador.py`, `aviso_telegram.py` |

`.gitignore` también deja fuera `venv/`, el modelo `*.pt` y las fotos y registros que genera el sistema (`*.jpg`, `*.log`), porque pueden mostrar a personas del aula.

### `credenciales.h`

```c
#define WIFI_NOMBRE     "ADMON"         // red de la universidad (internet)
#define WIFI_CONTRASENA "..."
#define AP_NOMBRE       "LAB8-CAMARA"   // red propia de la placa
#define AP_CONTRASENA   "..."           // mínimo 8 caracteres
#define SERVIDOR_URL    ""              // modo recibir: "https://<dominio>/foto"; "" = no enviar
#define CAMARA_CLAVE    "..."           // igual a "clave" en receptor.json
```

| Constante         | Descripción                                                                   |
| ----------------- | ----------------------------------------------------------------------------- |
| `WIFI_NOMBRE`     | Red con internet a la que se conecta la placa                                 |
| `WIFI_CONTRASENA` | Contraseña de esa red                                                         |
| `AP_NOMBRE`       | Nombre de la red que crea la placa (IP fija `192.168.4.1`)                    |
| `AP_CONTRASENA`   | Contraseña de esa red (mínimo 8 caracteres)                                   |
| `SERVIDOR_URL`    | Dónde enviar las fotos en el modo recibir. Vacía en el modo pedir             |
| `CAMARA_CLAVE`    | Clave que acompaña cada foto; debe coincidir con la de `receptor.json`        |

### `receptor.json`

Solo para el modo recibir:

```json
{"clave": "32 caracteres hexadecimales", "ngrok_dominio": "tu-dominio.ngrok-free.dev"}
```

| Campo           | Descripción                                                                         |
| --------------- | ----------------------------------------------------------------------------------- |
| `clave`         | Igual a `CAMARA_CLAVE`. Las fotos sin clave o con otra clave se rechazan (403)      |
| `ngrok_dominio` | Opcional. Con él se usa ngrok y la dirección no cambia; sin él, Cloudflare Tunnel   |

Genera la clave con:

```bash
openssl rand -hex 16
```

### `telegram.json`

```json
{"token": "123456:ABC...", "chat_id": "987654321"}
```

Para crear el bot:

1. En Telegram, escríbele `/newbot` a **@BotFather** y copia el token en `telegram.json`.
2. Abre tu bot y envíale `/start`.
3. Ejecuta `python aviso_telegram.py --buscar-chat` y copia el número en `chat_id`.
4. Ejecuta `python aviso_telegram.py --probar`; te debe llegar un mensaje de prueba.

### Ajustes en el código

| Constante            | Archivo                        | Por defecto                                | Qué controla                              |
| -------------------- | ------------------------------ | ------------------------------------------ | ----------------------------------------- |
| `NOMBRE_AULA`        | `contador.py`                  | `Laboratorio de Competencias Digitales 3`  | Nombre que aparece en los avisos          |
| `FOTOS_PARA_OCUPADA` | `contador.py`                  | `2`                                        | Fotos seguidas con gente para dar el aula por ocupada |
| `MINUTOS_SIN_CAMARA` | `contador.py`                  | `5`                                        | Minutos sin fotos antes del aviso de cámara caída |
| `SEGUNDOS_SIN_FOTO`  | `contador.py`                  | `15`                                       | En modo recibir, espera máxima por cada foto |
| `ENVIO_CADA_MS`      | `esp32s3-computer-vision.ino`  | `2500`                                     | Cada cuánto envía la placa una foto       |

## Uso

### Modo pedir: placa cerca (menos de ~20 m)

1. Conecta la placa al cargador y espera unos 15 segundos.
2. Conecta el WiFi del PC a la red de la placa: `nmcli connection up LAB8-CAMARA`.
3. Arranca el contador:

```bash
source venv/bin/activate

python contador.py                       # avisa tras 5 min vacía
python contador.py --minutos-vacio 0.5   # prueba rápida: avisa a los 30 s
python contador.py --sin-telegram        # solo consola, no envía nada
python contador.py --imagen foto.jpg     # analiza una foto guardada
python contador.py --confianza 0.3       # más sensible (y más errores)
```

> En este modo deja `SERVIDOR_URL ""` en `credenciales.h`: si apunta a una dirección donde nadie recibe, la placa pierde tiempo intentando enviar y `/capture` responde lento.

### Modo recibir: placa lejos (en el laboratorio)

ADMON no deja que dos equipos se hablen entre sí, pero sí deja que ambos salgan a internet. Por eso el flujo se invierte: **la placa envía** las fotos y el PC las recibe a través de un túnel.

```
Placa ──ADMON──► internet ──► https://<dominio>/foto ──túnel──► PC (receptor.py + contador.py) ──► 📱 Telegram
```

**Con ngrok (dirección fija, recomendado):**

1. Crea una cuenta en <https://ngrok.com>, reclama tu dominio gratuito y configura el authtoken una sola vez:

   ```bash
   ngrok config add-authtoken TU_AUTHTOKEN
   ```

2. Escribe el dominio en `ngrok_dominio` (`receptor.json`) y en `SERVIDOR_URL` (`credenciales.h`, terminado en `/foto`), y carga el firmware.
3. Arranca el contador:

   ```bash
   python contador.py --recibir
   # Tunel abierto. La placa debe enviar a: https://tu-dominio.ngrok-free.dev/foto
   ```

**Con Cloudflare Tunnel (sin cuenta):** quita `ngrok_dominio` de `receptor.json` y ejecuta `python contador.py --recibir`. La dirección `https://xxxx.trycloudflare.com` cambia cada vez que se reinicia, y entonces hay que actualizar `SERVIDOR_URL` y volver a cargar el firmware.

**Prueba local sin túnel:** con el PC en `LAB8-CAMARA`, pon `SERVIDOR_URL "http://192.168.4.2:8000/foto"` y ejecuta:

```bash
python contador.py --recibir --sin-tunel --host 192.168.4.2
```

### Opciones

| Opción            | Por defecto   | Qué hace                                                        |
| ----------------- | ------------- | --------------------------------------------------------------- |
| `--ip`            | `192.168.4.1` | IP de la placa (modo pedir)                                     |
| `--cada`          | `2`           | Segundos entre fotos (modo pedir)                               |
| `--minutos-vacio` | `5`           | Minutos seguidos sin nadie antes de avisar                      |
| `--confianza`     | `0.4`         | De 0 a 1: qué tan seguro debe estar YOLO para contar a alguien  |
| `--sin-telegram`  | —             | No envía avisos, solo consola                                   |
| `--imagen`        | —             | Analiza un archivo en vez de la cámara                          |
| `--recibir`       | —             | Recibe las fotos que envía la placa, en vez de pedirlas         |
| `--puerto`        | `8000`        | Puerto local del receptor                                       |
| `--sin-tunel`     | —             | No abre el túnel (pruebas locales)                              |
| `--host`          | `127.0.0.1`   | IP donde escucha el receptor                                    |

## Rutas

### Placa (`http://192.168.4.1`, con el PC en `LAB8-CAMARA`)

| Método | Ruta               | Descripción                                                            |
| ------ | ------------------ | ---------------------------------------------------------------------- |
| GET    | `/`                | Cámara en vivo, para apuntarla                                         |
| GET    | `/capture`         | Una foto JPEG (la usa `contador.py` en el modo pedir)                  |
| GET    | `/estado`          | Tiempo encendida, memoria, señal de ADMON, prueba de internet y envíos |
| GET    | `/probar-internet` | Repite la prueba de internet por ADMON                                 |

### Receptor (`contador.py --recibir`)

| Método | Ruta    | Descripción                                    | Auth              |
| ------ | ------- | ---------------------------------------------- | ----------------- |
| POST   | `/foto` | Recibe una foto JPEG de la placa (máx. 2 MB)   | Cabecera `X-Clave` |
| GET    | `/`     | Responde `contador activo` (comprobar el túnel) | No                |

## Prueba de punta a punta

1. Conecta la placa al cargador y espera unos 15 segundos.
2. Ejecuta `nmcli connection up LAB8-CAMARA` (o, en el modo recibir, comprueba en `/estado` que los envíos salen bien).
3. Ejecuta `python contador.py --minutos-vacio 0.5` (añade `--recibir` en el modo recibir).
4. Con gente frente a la cámara debe aparecer `Aula OCUPADA. Te avisare cuando quede vacia.`
5. Salgan todos de la vista de la cámara. La consola cuenta `No se detecta a nadie (12 s de 30 s)`.
6. A los 30 segundos llega al celular la foto del aula vacía con el aviso.
7. **Corte de energía:** desconecta el cargador más de 5 minutos. Debe llegar *"No recibo fotos de la camara..."* y, al reconectarlo, *"...volvio a funcionar."*

## Solución de problemas

| Síntoma | Causa | Solución |
| --- | --- | --- |
| `No pude conectar con el ESP32. Esta encendido y tu WiFi en LAB8-CAMARA?` | La placa se reinició y el PC se pasó a otra red | Espera unos 15 s tras encender la placa y ejecuta `nmcli connection up LAB8-CAMARA` |
| `No llegan fotos de la placa hace 15 s` | Modo recibir: la placa no tiene internet, o `SERVIDOR_URL` no coincide con el túnel | Revisa `/estado` en la placa: el último envío dice el código de error (403 = clave distinta) |
| Las fotos tardan o `/capture` falla a ratos | `SERVIDOR_URL` apunta a una dirección donde nadie recibe | En el modo pedir deja `SERVIDOR_URL ""` y vuelve a cargar el firmware |
| La red `LAB8-CAMARA` no aparece | La placa no arrancó, o la cámara falló y se reinicia cada 10 s | Conéctala por USB, lee el log a 115200 baudios y revisa el cable flex |
| `No route to host` hacia una IP `172.18.x.x` | La red de Docker (`docker0`) usa las mismas direcciones que ADMON | Usa la red `LAB8-CAMARA` (`192.168.4.1`), no la IP de la placa en ADMON |
| `ngrok se cerro. Configuraste el authtoken?` | Falta el authtoken o el dominio no es tuyo | Ejecuta `ngrok config add-authtoken ...` y revisa `ngrok_dominio` |
| `Falta telegram.json` | El bot no está configurado | Ver [`telegram.json`](#telegramjson), o ejecuta con `--sin-telegram` |
| `No pude enviar el Telegram: ...` | Sin internet, o token o `chat_id` incorrectos | Ejecuta `python aviso_telegram.py --probar` |
| No cuenta a alguien que sí está | Persona tapada, de espaldas o con mala luz | Ubica la cámara más alta y de frente al aula; prueba `--confianza 0.3` |
| La placa se reinicia sola con el cargador | El cargador da poca corriente | Usa un cargador de 5 V y al menos 1 A con un cable de calidad |
| Falla `arduino-cli upload` | La placa no entra en modo de carga | Mantén pulsado BOOT, pulsa y suelta RST, y vuelve a intentarlo |

## Estado y pendientes

| Etapa         | Resultado                                                                                     |
| ------------- | --------------------------------------------------------------------------------------------- |
| 1. Cámara     | Fotos de 640x480 recibidas por USB (2026-09-30)                                               |
| 2. Detección  | YOLO cuenta personas en vivo por WiFi: 3 de 3 en la oficina                                   |
| 3. Aviso      | Telegram con foto al quedar vacía, probado de punta a punta (2026-10-01)                     |
| 4. Producción | La placa envía las fotos por ADMON a una dirección fija de ngrok; probado el 2026-10-14       |

- [x] Salida a internet desde ADMON: DNS, HTTP 80 y HTTPS 443; subir una foto de 27 KB tarda ~1,2 s (2026-10-01).
- [x] Envío de fotos con clave `X-Clave`: ~0,2 s por foto en red local (2026-10-13).
- [x] Placa → ADMON → túnel → PC por internet: una foto cada 2–5 s, conteo correcto (2026-10-14).
- [ ] Instalar la placa en el laboratorio y repetir la [prueba de punta a punta](#prueba-de-punta-a-punta), incluido el corte de energía.
- [ ] Revocar los tokens que quedaron expuestos: bot de Telegram (`/revoke` en @BotFather) y authtoken de ngrok (*Reset* en el panel).
- [ ] Verificar el certificado HTTPS en la placa (hoy usa `setInsecure`). Probado el 2026-10-21: verificar la cadena ECDSA P-384 de Let's Encrypt que usa ngrok tarda más de 2 s en el ESP32-S3 y ngrok corta la conexión. La clave `X-Clave` impide que otros envíen fotos.
- [ ] Privacidad (Ley 1581 de protección de datos personales): las fotos se analizan y se descartan; solo se conserva la del aula vacía.
- [ ] Mover el contador del portátil a un servidor permanente (de la universidad o en la nube).
- [ ] Alternativa sin servidor: que la placa detecte por sí sola si hay alguien y envíe el Telegram.

## Autor

- GitHub: <https://github.com/jairprime>
- Email: <jairenriquez1715@gmail.com>
