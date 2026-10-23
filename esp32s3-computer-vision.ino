// Camara del Laboratorio de Competencias Digitales 3
// El ESP32 crea su propia red WiFi ("LAB8-CAMARA") y funciona como un pequeno
// servidor web. Con el PC conectado a esa red:
//   http://192.168.4.1/                 pagina para ver la camara en el navegador
//   http://192.168.4.1/capture          una foto JPEG (la pide contador.py en el PC)
//   http://192.168.4.1/estado           estado de la placa y resultado de la prueba de internet
//   http://192.168.4.1/probar-internet  repite la prueba de internet por ADMON
// Ademas, si SERVIDOR_URL tiene una direccion, envia una foto cada ENVIO_CADA_MS
// por internet (a traves de ADMON) al contador que corre en el portatil o servidor.

#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include "esp_camera.h"
#include "credenciales.h"

// Pines de la camara en la placa ESP32-S3-WROOM CAM (N16R8).
// Es el mismo mapa que "CAMERA_MODEL_ESP32S3_EYE" de los ejemplos de Arduino.
#define PWDN_GPIO_NUM  -1
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM  15
#define SIOD_GPIO_NUM  4
#define SIOC_GPIO_NUM  5
#define Y2_GPIO_NUM    11
#define Y3_GPIO_NUM    9
#define Y4_GPIO_NUM    8
#define Y5_GPIO_NUM    10
#define Y6_GPIO_NUM    12
#define Y7_GPIO_NUM    18
#define Y8_GPIO_NUM    17
#define Y9_GPIO_NUM    16
#define VSYNC_GPIO_NUM 6
#define HREF_GPIO_NUM  7
#define PCLK_GPIO_NUM  13

#define BAUDIOS 115200

WebServer servidor(80);  // puerto 80 = el puerto normal de las paginas web
bool camaraLista = false;
String resultadoInternet = "todavia no se ha probado";

#define ENVIO_CADA_MS 2500  // una foto cada 2,5 s es suficiente para saber si hay gente
unsigned long ultimoEnvio = 0;
unsigned long enviosOk = 0, enviosFallidos = 0;
String ultimoEnvioTexto = "ninguno todavia";
// Cliente HTTPS que se reutiliza entre fotos: abrir una conexion cifrada nueva
// tarda ~1 s, reutilizarla es mucho mas rapido.
WiFiClientSecure clienteServidor;  // para direcciones https:// (tunel, servidor en internet)
WiFiClient clienteLocal;           // para direcciones http:// (pruebas en la red local)
HTTPClient httpServidor;

bool iniciarCamara() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;  // la camara entrega la foto ya comprimida
  config.frame_size = FRAMESIZE_VGA;     // 640x480
  config.jpeg_quality = 12;              // 0-63, menor = mejor calidad
  config.fb_count = 2;                   // dos fotos en memoria: mientras una se envia, se toma la otra
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode = CAMERA_GRAB_LATEST;  // siempre la foto mas reciente

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("ERROR: la camara no inicio (codigo 0x%x)\n", err);
    return false;
  }

  sensor_t *s = esp_camera_sensor_get();
  Serial.printf("Camara OK. Sensor PID=0x%04x\n", s->id.PID);
  return true;
}

// La placa hace dos cosas a la vez (modo AP_STA):
//  - AP:  crea su propia red WiFi. Su IP ahi es SIEMPRE 192.168.4.1.
//         Hace falta porque la red ADMON no deja que los equipos WiFi se vean entre si.
//  - STA: se conecta a ADMON, como un celular, para tener internet (avisos en la etapa 3).
void iniciarWifi() {
  WiFi.mode(WIFI_AP_STA);
  WiFi.setSleep(false);  // sin ahorro de energia: responde mas rapido

  WiFi.softAP(AP_NOMBRE, AP_CONTRASENA);
  Serial.printf("Red propia \"%s\" lista. Conecta tu PC y abre http://%s/\n",
                AP_NOMBRE, WiFi.softAPIP().toString().c_str());

  WiFi.setAutoReconnect(true);  // si ADMON se cae, la placa reconecta sola
  WiFi.begin(WIFI_NOMBRE, WIFI_CONTRASENA);
  Serial.printf("Conectando a \"%s\"", WIFI_NOMBRE);
  // Esperamos maximo 20 s; si ADMON no responde, la red propia sigue funcionando.
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("ADMON OK (IP %s), hay internet\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("ADMON no conecto todavia; seguira intentando sola");
  }
}

// Responde a /capture con una foto JPEG.
void enviarFoto() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    servidor.send(503, "text/plain", "no se pudo tomar la foto");
    return;
  }
  servidor.sendHeader("Cache-Control", "no-store");
  servidor.send_P(200, "image/jpeg", (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
}

// Prueba si la placa puede salir a internet por ADMON. Es lo que necesitara en
// produccion: enviar fotos a un servidor o mensajes a Telegram.
String probarUnaUrl(const char *nombre, const char *url, bool segura,
                    const uint8_t *datos = nullptr, size_t largo = 0) {
  WiFiClient normal;
  WiFiClientSecure cifrado;
  // Para esta prueba no verificamos el certificado HTTPS (setInsecure); solo
  // queremos saber si la red deja pasar la conexion.
  cifrado.setInsecure();
  HTTPClient http;
  http.setTimeout(15000);
  http.begin(segura ? (WiFiClient &)cifrado : normal, url);
  unsigned long inicio = millis();
  int codigo;
  if (datos) {
    http.addHeader("Content-Type", "image/jpeg");
    codigo = http.POST((uint8_t *)datos, largo);
  } else {
    codigo = http.GET();
  }
  unsigned long ms = millis() - inicio;
  http.end();
  // codigo > 0 = el servidor respondio (aunque sea un 302 o un 404): la red dejo pasar.
  if (codigo > 0) return String("OK    ") + nombre + " (codigo " + codigo + ", " + ms + " ms)\n";
  return String("FALLA ") + nombre + " (" + HTTPClient::errorToString(codigo) + ")\n";
}

void probarInternet() {
  if (WiFi.status() != WL_CONNECTED) {
    resultadoInternet = "FALLA ADMON no esta conectada\n";
    Serial.print(resultadoInternet);
    return;
  }
  Serial.println("Probando internet por ADMON...");
  String r;
  IPAddress ip;
  if (WiFi.hostByName("api.telegram.org", ip)) {
    r += "OK    DNS: api.telegram.org = " + ip.toString() + "\n";
  } else {
    r += "FALLA DNS: no pudo traducir nombres a direcciones IP\n";
  }
  r += probarUnaUrl("HTTP, puerto 80 (example.com)", "http://example.com/", false);
  r += probarUnaUrl("HTTPS, puerto 443 (api.telegram.org)", "https://api.telegram.org/", true);
  // Sube datos de relleno del tamano de una foto: asi sabremos cuanto tarda subir
  // cada foto, sin enviar imagenes del aula (con personas) a un servicio de terceros.
  const size_t TAMANO_FOTO = 30000;  // una foto VGA pesa ~30 KB
  uint8_t *relleno = (uint8_t *)ps_calloc(TAMANO_FOTO, 1);
  if (relleno) {
    r += probarUnaUrl("Subir 30 KB de prueba (httpbin.org)", "https://httpbin.org/post", true,
                      relleno, TAMANO_FOTO);
    free(relleno);
  }
  resultadoInternet = r;
  Serial.print(r);
}

// Responde a /estado con texto simple.
void enviarEstado() {
  String t = "Placa: encendida hace " + String(millis() / 1000) + " s\n";
  t += "Memoria libre: " + String(ESP.getFreeHeap()) + " bytes (PSRAM " + String(ESP.getFreePsram()) + ")\n";
  if (WiFi.status() == WL_CONNECTED) {
    t += "ADMON: conectada, IP " + WiFi.localIP().toString() + ", senal " + String(WiFi.RSSI()) + " dBm\n";
  } else {
    t += "ADMON: desconectada\n";
  }
  t += "Equipos conectados a LAB8-CAMARA: " + String(WiFi.softAPgetStationNum()) + "\n\n";
  t += "Prueba de internet:\n" + resultadoInternet + "\n";
  if (strlen(SERVIDOR_URL) == 0) {
    t += "Envio de fotos: desactivado (SERVIDOR_URL vacio)\n";
  } else {
    t += "Envio de fotos a " + String(SERVIDOR_URL) + "\n";
    t += "  correctos: " + String(enviosOk) + ", fallidos: " + String(enviosFallidos) + "\n";
    t += "  ultimo: " + ultimoEnvioTexto + "\n";
  }
  servidor.send(200, "text/plain; charset=utf-8", t);
}

void repetirPruebaInternet() {
  probarInternet();
  enviarEstado();
}

// Responde a / con una pagina que recarga la foto cada segundo.
void enviarPagina() {
  servidor.send(200, "text/html",
    "<!doctype html><meta name=viewport content='width=device-width'>"
    "<title>Camara ESP32-S3</title>"
    "<body style='margin:0;background:#111;color:#eee;font-family:sans-serif;text-align:center'>"
    "<h3>Camara ESP32-S3</h3><img id=f style='max-width:100%'>"
    "<script>const f=document.getElementById('f');"
    "function r(){f.src='/capture?t='+Date.now();}f.onload=()=>setTimeout(r,1000);f.onerror=()=>setTimeout(r,2000);r();</script>");
}

void setup() {
  Serial.begin(BAUDIOS);
  delay(500);
  Serial.println();
  Serial.println("=== Camara Laboratorio de Competencias Digitales 3 ===");
  camaraLista = iniciarCamara();
  if (!camaraLista) {
    Serial.println("Sin camara. Revisa el cable flex. Reintento en 10 s...");
    return;
  }
  iniciarWifi();
  servidor.on("/", enviarPagina);
  servidor.on("/capture", enviarFoto);
  servidor.on("/estado", enviarEstado);
  servidor.on("/probar-internet", repetirPruebaInternet);
  servidor.begin();
  probarInternet();

  // No se verifica el certificado HTTPS del tunel. Se probo (2026-10-21): la cadena
  // ECDSA P-384 de Let's Encrypt que usa ngrok tarda mas de 2 s en verificarse en el
  // ESP32-S3 (no acelera esas curvas por hardware) y ngrok corta la conexion a los
  // 2 s. La clave X-Clave sigue impidiendo que otros envien fotos al contador.
  clienteServidor.setInsecure();
  httpServidor.setReuse(true);
  httpServidor.setConnectTimeout(8000);
  httpServidor.setTimeout(10000);
}

// Envia una foto al contador por internet, con la clave en la cabecera X-Clave.
void enviarFotoAlServidor() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    enviosFallidos++;
    ultimoEnvioTexto = "no se pudo tomar la foto";
    return;
  }
  unsigned long inicio = millis();
  bool segura = strncmp(SERVIDOR_URL, "https://", 8) == 0;
  httpServidor.begin(segura ? (WiFiClient &)clienteServidor : clienteLocal, SERVIDOR_URL);
  httpServidor.addHeader("Content-Type", "image/jpeg");
  httpServidor.addHeader("X-Clave", CAMARA_CLAVE);
  int codigo = httpServidor.POST(fb->buf, fb->len);
  httpServidor.end();  // con setReuse(true) la conexion queda abierta para la siguiente foto
  esp_camera_fb_return(fb);

  unsigned long ms = millis() - inicio;
  if (codigo == 200) {
    enviosOk++;
    ultimoEnvioTexto = "OK en " + String(ms) + " ms";
  } else {
    enviosFallidos++;
    // codigo < 0: no hubo conexion (contador apagado, tunel cerrado, sin internet).
    // 403: la clave no coincide con la de receptor.json.
    ultimoEnvioTexto = codigo > 0 ? "codigo " + String(codigo) : HTTPClient::errorToString(codigo);
    // En https, "connection refused" tambien sale cuando falla la conexion cifrada:
    // el detalle real lo da el cliente seguro.
    char detalle[100];
    if (codigo < 0 && segura && clienteServidor.lastError(detalle, sizeof(detalle)) != 0) {
      ultimoEnvioTexto += String(" (TLS: ") + detalle + ")";
    }
    Serial.println("Envio fallido: " + ultimoEnvioTexto);
  }
}

void loop() {
  // Si la camara fallo al encender (por ejemplo, un falso contacto del flex),
  // reiniciamos la placa sola en vez de quedarnos colgados para siempre.
  // Importante cuando nadie esta mirando la placa en el laboratorio.
  if (!camaraLista) {
    delay(10000);
    ESP.restart();
  }
  servidor.handleClient();  // atiende las peticiones que lleguen

  if (strlen(SERVIDOR_URL) > 0 && WiFi.status() == WL_CONNECTED &&
      millis() - ultimoEnvio >= ENVIO_CADA_MS) {
    ultimoEnvio = millis();
    enviarFotoAlServidor();
  }
}
