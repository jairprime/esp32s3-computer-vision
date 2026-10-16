"""Recibe las fotos que la placa envia por internet.

Como ADMON no deja que los equipos se hablen entre si, la placa no puede enviarle
las fotos directo a tu portatil. Por eso:
  1. Este modulo abre un pequeno servidor web en tu portatil (solo local: 127.0.0.1).
  2. Un tunel (ngrok o Cloudflare Tunnel) le da una direccion publica https://...
     que llega a ese servidor. Tanto la placa como tu portatil solo SALEN a internet,
     que es lo que ADMON si permite.
  3. La placa envia cada foto con una clave secreta; las que no traen la clave se rechazan.

La configuracion se guarda en receptor.json (no lo compartas):
  {"clave": "...", "ngrok_dominio": "tu-nombre.ngrok-free.dev"}

"ngrok_dominio" es opcional:
  - Con el: se usa ngrok y la direccion es SIEMPRE la misma (para produccion).
  - Sin el: se usa el tunel rapido de Cloudflare, cuya direccion cambia en cada inicio.
"""
import hmac
import json
import pathlib
import re
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CONFIG = pathlib.Path(__file__).with_name("receptor.json")
TAMANO_MAXIMO = 2_000_000  # una foto VGA pesa ~30 KB; esto rechaza envios absurdos


def cargar_config():
    if not CONFIG.exists():
        raise SystemExit(f"Falta {CONFIG.name} con la clave de la camara (ver README).")
    return json.loads(CONFIG.read_text())


def cargar_clave():
    return cargar_config()["clave"]


class Receptor:
    """Servidor web que guarda la ultima foto recibida."""

    def __init__(self, clave, puerto, host="127.0.0.1"):
        self.clave = clave.encode()
        self.numero = 0          # cuantas fotos validas han llegado
        self.ultima = None       # (numero, bytes del JPEG)
        self.candado = threading.Lock()  # el servidor y el contador usan self.ultima a la vez
        receptor = self

        class Manejador(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path != "/foto":
                    return self.responder(404, "no existe")
                # compare_digest compara sin filtrar pistas por el tiempo que tarda
                clave = self.headers.get("X-Clave", "").encode()
                if not hmac.compare_digest(clave, receptor.clave):
                    return self.responder(403, "clave incorrecta")
                try:
                    largo = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    return self.responder(400, "Content-Length invalido")
                if not 0 < largo <= TAMANO_MAXIMO:
                    return self.responder(413, "tamano invalido")
                receptor.guardar(self.rfile.read(largo))
                self.responder(200, "ok")

            def do_GET(self):
                self.responder(200, "contador activo")

            def responder(self, codigo, texto):
                cuerpo = texto.encode()
                self.send_response(codigo)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)

            def log_message(self, *args):
                pass  # sin esto, imprime una linea por cada foto

        # 127.0.0.1 (por defecto): solo se llega desde este mismo portatil, o sea, desde
        # el tunel. Para pruebas locales se puede usar la IP del portatil en LAB8-CAMARA.
        try:
            self.servidor = ThreadingHTTPServer((host, puerto), Manejador)
        except OSError as error:
            raise SystemExit(f"No pude abrir el puerto {puerto} en {host} ({error.strerror}). "
                             "Hay otro contador corriendo?")
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()

    def guardar(self, datos):
        with self.candado:
            self.numero += 1
            self.ultima = (self.numero, datos)

    def esperar_foto(self, ultimo_numero, espera):
        """Devuelve (numero, jpeg) de una foto mas nueva que ultimo_numero.

        Si no llega ninguna en `espera` segundos, devuelve None.
        """
        limite = time.monotonic() + espera
        while time.monotonic() < limite:
            with self.candado:
                ultima = self.ultima
            if ultima and ultima[0] != ultimo_numero:
                return ultima
            time.sleep(0.1)
        return None


def abrir_tunel(puerto):
    """Abre el tunel que corresponda segun receptor.json. Devuelve (proceso, url)."""
    dominio = cargar_config().get("ngrok_dominio")
    if dominio:
        return abrir_tunel_ngrok(puerto, dominio)
    return abrir_tunel_cloudflare(puerto)


def arrancar(comando):
    """Arranca un programa externo (ngrok o cloudflared) leyendo su salida de errores."""
    try:
        return subprocess.Popen(comando, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError:
        raise SystemExit(f"No encuentro el programa '{comando[0]}'. Instalalo (ver README).")


def abrir_tunel_ngrok(puerto, dominio, espera=30):
    """Arranca ngrok con tu dominio fijo y devuelve (proceso, url publica).

    Antes, una sola vez: ngrok config add-authtoken TU_TOKEN
    """
    proceso = arrancar(
        ["ngrok", "http", f"127.0.0.1:{puerto}", "--url", f"https://{dominio}", "--log", "stderr"])
    errores = []
    threading.Thread(target=lambda: [errores.append(l) for l in proceso.stderr], daemon=True).start()
    # ngrok tiene una pagina local (puerto 4040) que dice que tuneles tiene abiertos.
    limite = time.monotonic() + espera
    while time.monotonic() < limite:
        if proceso.poll() is not None:  # ngrok se cerro: normalmente falta el authtoken
            detalle = next((l.strip() for l in errores if "ERR" in l or "lvl=eror" in l), "")
            raise SystemExit(f"ngrok se cerro. Configuraste el authtoken? {detalle}")
        try:
            with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=2) as r:
                for t in json.load(r)["tunnels"]:
                    if t["public_url"].startswith("https://"):
                        return proceso, t["public_url"]
        except OSError:
            pass  # todavia arrancando
        time.sleep(1)
    proceso.terminate()
    raise SystemExit("ngrok no abrio el tunel a tiempo. Hay internet en este portatil?")


def abrir_tunel_cloudflare(puerto, espera=60):
    """Arranca cloudflared (tunel rapido, sin cuenta) y devuelve (proceso, url publica)."""
    proceso = arrancar(
        ["cloudflared", "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{puerto}"])
    encontrada = {}
    listo = threading.Event()

    def leer_salida():
        # cloudflared escribe la direccion en su salida de errores. Hay que leerla
        # siempre, aunque ya tengamos la URL: si nadie la lee, cloudflared se bloquea.
        for linea in proceso.stderr:
            m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", linea)
            if m and not listo.is_set():
                encontrada["url"] = m.group(0)
                listo.set()

    threading.Thread(target=leer_salida, daemon=True).start()
    if not listo.wait(espera):
        proceso.terminate()
        raise SystemExit("cloudflared no entrego una direccion. Hay internet en este portatil?")
    return proceso, encontrada["url"]
