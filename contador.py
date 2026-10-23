"""Contador de personas con aviso por Telegram.

Recibe fotos del ESP32, cuenta cuantas personas hay con el modelo YOLO y te
avisa por Telegram cuando el laboratorio queda vacio. Guarda la ultima foto con
los recuadros dibujados en deteccion.jpg para que veas que detecto.

Dos formas de recibir las fotos:
  - Pedirlas (por defecto): el portatil conectado a la red LAB8-CAMARA de la placa.
    Solo sirve cerca de la placa (unos 20 m).
  - Recibirlas (--recibir): la placa las envia por internet a traves de un tunel.
    Sirve con la placa en el laboratorio y el portatil en ADMON o en el cable.

Uso (con el entorno activado: source venv/bin/activate):
  python contador.py --recibir             (placa lejos: recibe por internet)
  python contador.py                       (placa cerca: pide por LAB8-CAMARA)
  python contador.py --minutos-vacio 0.5   (para probar rapido en la oficina)
  python contador.py --sin-telegram        (solo consola, no envia nada)
  python contador.py --imagen foto.jpg     (probar con una foto guardada)
"""
import argparse
import pathlib
import time
from datetime import datetime

import cv2
import numpy as np
import requests
import torch
from ultralytics import YOLO

import aviso_telegram
import receptor

# NNPACK es una aceleracion que el procesador de este PC no soporta. Sin esto,
# PyTorch imprime "Could not initialize NNPACK" en cada foto. No cambia el resultado.
torch.backends.nnpack.set_flags(False)

CARPETA = pathlib.Path(__file__).parent
IP_POR_DEFECTO = "192.168.4.1"  # IP fija de la placa en su red propia LAB8-CAMARA
CLASE_PERSONA = 0  # en el modelo YOLO la clase 0 es "person"
FOTOS_PARA_OCUPADA = 2  # fotos seguidas con gente para dar el aula por ocupada
MINUTOS_SIN_CAMARA = 5  # si la camara no responde este tiempo, te avisa
NOMBRE_AULA = "Laboratorio de Competencias Digitales 3"  # aparece en los avisos
SEGUNDOS_SIN_FOTO = 15  # en modo --recibir: sin fotos nuevas este tiempo = fallo


class VigilanteAula:
    """Decide cuando avisar, a partir del numero de personas de cada foto.

    Estados:
      "libre"    el aula no se ha usado todavia (o ya se aviso que quedo vacia)
      "ocupada"  hay o hubo gente hace poco

    libre -> ocupada:  FOTOS_PARA_OCUPADA fotos seguidas con al menos 1 persona.
                       Pedir varias evita que un error en una sola foto cuente.
    ocupada -> libre:  todas las fotos en 0 durante segundos_vacio seguidos.
                       Si en ese tiempo aparece alguien, la cuenta vuelve a empezar.
                       Este cambio es el que dispara el aviso de cerrar.
    """

    def __init__(self, segundos_vacio):
        self.segundos_vacio = segundos_vacio
        self.estado = "libre"
        self.fotos_con_gente = 0
        self.vacio_desde = None
        self.maximo = 0  # cuantas personas hubo como maximo mientras estuvo ocupada

    def actualizar(self, personas, ahora):
        """Devuelve "ocupada" o "vacia" cuando cambia el estado, si no None."""
        if self.estado == "libre":
            self.fotos_con_gente = self.fotos_con_gente + 1 if personas > 0 else 0
            if self.fotos_con_gente >= FOTOS_PARA_OCUPADA:
                self.estado = "ocupada"
                self.maximo = personas
                self.vacio_desde = None
                return "ocupada"
            return None

        # estado "ocupada"
        if personas > 0:
            self.maximo = max(self.maximo, personas)
            self.vacio_desde = None
            return None
        if self.vacio_desde is None:
            self.vacio_desde = ahora
        if ahora - self.vacio_desde >= self.segundos_vacio:
            self.estado = "libre"
            self.fotos_con_gente = 0
            return "vacia"
        return None

    def segundos_vacia(self, ahora):
        return 0 if self.vacio_desde is None else ahora - self.vacio_desde


def contar_personas(modelo, imagen, confianza):
    """Devuelve (numero de personas, imagen con recuadros)."""
    resultado = modelo(imagen, classes=[CLASE_PERSONA], conf=confianza, verbose=False)[0]
    return len(resultado.boxes), resultado.plot()


class FotoDanada(Exception):
    pass


class SinFotos(Exception):
    pass


def pedir_foto(ip):
    respuesta = requests.get(f"http://{ip}/capture", timeout=10)
    respuesta.raise_for_status()
    return decodificar(respuesta.content)


def decodificar(jpeg):
    datos = np.frombuffer(jpeg, dtype=np.uint8)
    foto = cv2.imdecode(datos, cv2.IMREAD_COLOR)
    # Si el JPEG llego cortado, imdecode devuelve None. Hay que descartarlo: con None,
    # YOLO analiza sus propias fotos de ejemplo y contaria personas que no existen.
    if foto is None:
        raise FotoDanada(f"llegaron {len(datos)} bytes que no forman un JPEG valido")
    return foto


def hora_actual():
    """Hora en formato de 12 horas, por ejemplo 4:48:45 PM.

    Se arma a mano en vez de usar %p: %p depende del idioma del sistema y en
    espanol puede salir vacio o como "p. m.".
    """
    ahora = datetime.now()
    return f"{ahora.hour % 12 or 12}:{ahora:%M:%S} {'AM' if ahora.hour < 12 else 'PM'}"


def avisar(usar_telegram, hora, texto, imagen=None):
    """Imprime el aviso y lo envia por Telegram. Si Telegram falla, el contador sigue."""
    print(f"[{hora}] >>> AVISO: {texto}")
    if not usar_telegram:
        return
    try:
        if imagen is None:
            aviso_telegram.enviar_mensaje(texto)
        else:
            aviso_telegram.enviar_foto(cv2.imencode(".jpg", imagen)[1].tobytes(), texto)
    except Exception as error:  # sin internet, token mal escrito, etc.
        print(f"[{hora}] No pude enviar el Telegram: {error}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", default=IP_POR_DEFECTO, help="IP del ESP32")
    parser.add_argument("--imagen", help="analizar una foto guardada en vez de la camara")
    parser.add_argument("--confianza", type=float, default=0.4,
                        help="0 a 1: que tan seguro debe estar el modelo para contar a alguien")
    parser.add_argument("--cada", type=float, default=2, help="segundos entre fotos")
    parser.add_argument("--minutos-vacio", type=float, default=5,
                        help="minutos seguidos sin nadie para avisar que quedo vacio")
    parser.add_argument("--sin-telegram", action="store_true", help="no enviar avisos, solo consola")
    parser.add_argument("--recibir", action="store_true",
                        help="recibir las fotos que la placa envia por internet (placa lejos)")
    parser.add_argument("--puerto", type=int, default=8000, help="puerto local del receptor")
    parser.add_argument("--sin-tunel", action="store_true",
                        help="con --recibir: no abrir el tunel (pruebas locales)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="con --recibir: IP donde escucha el receptor (pruebas: 192.168.4.2)")
    args = parser.parse_args()

    # yolo11n = version "nano" del modelo: la mas liviana, suficiente para un PC sin GPU.
    # La primera vez se descarga sola (unos 5 MB).
    modelo = YOLO(CARPETA / "yolo11n.pt")

    if args.imagen:
        imagen = cv2.imread(args.imagen)
        if imagen is None:
            print(f"No pude abrir la imagen {args.imagen}")
            return
        personas, dibujada = contar_personas(modelo, imagen, args.confianza)
        cv2.imwrite(str(CARPETA / "deteccion.jpg"), dibujada)
        print(f"Personas en {args.imagen}: {personas}")
        return

    usar_telegram = not args.sin_telegram
    if usar_telegram:
        aviso_telegram.cargar_config()  # si falta telegram.json, se detiene aqui con el motivo

    tunel = None
    if args.recibir:
        rec = receptor.Receptor(receptor.cargar_clave(), args.puerto, args.host)
        ultimo_numero = None

        def obtener_foto():
            nonlocal ultimo_numero
            nueva = rec.esperar_foto(ultimo_numero, SEGUNDOS_SIN_FOTO)
            if nueva is None:
                raise SinFotos(f"no llegan fotos de la placa hace {SEGUNDOS_SIN_FOTO} s")
            ultimo_numero, jpeg = nueva
            return decodificar(jpeg)

        print(f"Receptor escuchando en http://{args.host}:{args.puerto}/foto")
        if not args.sin_tunel:
            tunel, url = receptor.abrir_tunel(args.puerto)
            print(f"Tunel abierto. La placa debe enviar a: {url}/foto")
    else:
        def obtener_foto():
            return pedir_foto(args.ip)

        print(f"Leyendo la camara en http://{args.ip}/")

    vigilante = VigilanteAula(args.minutos_vacio * 60)
    ultima_foto_ok = time.monotonic()
    camara_caida = False

    print("(Ctrl+C para salir)")
    print(f"Avisara cuando el aula lleve {args.minutos_vacio:g} min vacia"
          + ("" if usar_telegram else "  [Telegram desactivado]"))
    try:
        while True:
            try:
                foto = obtener_foto()
                error = None
            except (requests.RequestException, FotoDanada, SinFotos) as e:
                error = e
            # La hora se toma DESPUES de obtener la foto: en modo --recibir, obtener_foto
            # puede esperar varios segundos a que llegue la siguiente.
            hora = hora_actual()
            # monotonic() es un reloj que nunca retrocede: sirve para medir tiempos
            # aunque cambie la hora del PC.
            ahora = time.monotonic()
            if error:
                if isinstance(error, requests.ConnectionError):
                    print(f"[{hora}] No pude conectar con el ESP32. Esta encendido y tu WiFi en LAB8-CAMARA?")
                elif isinstance(error, SinFotos):
                    print(f"[{hora}] {str(error).capitalize()}. Esta encendida y conectada a ADMON?")
                else:
                    print(f"[{hora}] Foto descartada: {error}")
                if not camara_caida and ahora - ultima_foto_ok >= MINUTOS_SIN_CAMARA * 60:
                    camara_caida = True
                    avisar(usar_telegram, hora,
                           f"No recibo fotos de la camara del {NOMBRE_AULA} desde hace "
                           f"{MINUTOS_SIN_CAMARA} min. Revisa la placa.")
                time.sleep(args.cada)
                continue

            ultima_foto_ok = ahora
            if camara_caida:
                camara_caida = False
                avisar(usar_telegram, hora, f"La camara del {NOMBRE_AULA} volvio a funcionar.")

            personas, dibujada = contar_personas(modelo, foto, args.confianza)
            cv2.imwrite(str(CARPETA / "deteccion.jpg"), dibujada)
            evento = vigilante.actualizar(personas, ahora)

            if personas > 0:
                print(f"[{hora}] Personas: {personas}")
            elif vigilante.estado == "ocupada":
                print(f"[{hora}] No se detecta a nadie "
                      f"({vigilante.segundos_vacia(ahora):.0f} s de {vigilante.segundos_vacio:.0f} s)")
            else:
                print(f"[{hora}] No se detecta a nadie")

            if evento == "ocupada":
                print(f"[{hora}] Aula OCUPADA. Te avisare cuando quede vacia.")
            elif evento == "vacia":
                avisar(usar_telegram, hora,
                       f"El {NOMBRE_AULA} quedo vacio ({hora}). Hubo hasta {vigilante.maximo} "
                       f"{'persona' if vigilante.maximo == 1 else 'personas'}. "
                       f"Ya puedes ir a cerrarlo.", dibujada)
            # En modo --recibir no hace falta esperar: esperar_foto ya espera la siguiente.
            if not args.recibir:
                time.sleep(args.cada)
    except KeyboardInterrupt:
        print("Fin.")
    finally:
        if tunel:
            tunel.terminate()


if __name__ == "__main__":
    main()
