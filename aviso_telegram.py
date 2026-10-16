"""Envia mensajes y fotos a tu Telegram usando un bot.

El token del bot y tu chat_id se guardan en telegram.json (no lo compartas):
  {"token": "123456:ABC...", "chat_id": "987654321"}

Uso suelto (con el entorno activado):
  python aviso_telegram.py --buscar-chat   muestra tu chat_id (antes escribele /start a tu bot)
  python aviso_telegram.py --probar        envia un mensaje de prueba
"""
import argparse
import json
import pathlib

import requests

CONFIG = pathlib.Path(__file__).with_name("telegram.json")
API = "https://api.telegram.org/bot{token}/{metodo}"


def cargar_config():
    if not CONFIG.exists():
        raise SystemExit(f"Falta {CONFIG.name}. Crealo con tu token y chat_id (ver instrucciones).")
    return json.loads(CONFIG.read_text())


def llamar(token, metodo, **kwargs):
    respuesta = requests.post(API.format(token=token, metodo=metodo), timeout=20, **kwargs)
    datos = respuesta.json()
    if not datos.get("ok"):
        raise RuntimeError(f"Telegram respondio: {datos.get('description')}")
    return datos["result"]


def enviar_mensaje(texto):
    config = cargar_config()
    llamar(config["token"], "sendMessage", data={"chat_id": config["chat_id"], "text": texto})


def enviar_foto(jpeg_bytes, texto):
    config = cargar_config()
    llamar(config["token"], "sendPhoto",
           data={"chat_id": config["chat_id"], "caption": texto},
           files={"photo": ("aula.jpg", jpeg_bytes, "image/jpeg")})


def buscar_chat(token):
    """Muestra el chat_id de quien le haya escrito al bot."""
    mensajes = llamar(token, "getUpdates")
    if not mensajes:
        print("No hay mensajes. Abre tu bot en Telegram, escribele /start y vuelve a ejecutar esto.")
        return
    for m in mensajes:
        chat = m.get("message", {}).get("chat")
        if chat:
            print(f"chat_id = {chat['id']}  ({chat.get('first_name', '')} {chat.get('last_name', '')})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--buscar-chat", action="store_true")
    parser.add_argument("--probar", action="store_true")
    args = parser.parse_args()

    if args.buscar_chat:
        buscar_chat(cargar_config()["token"])
    elif args.probar:
        enviar_mensaje("Hola! El contador del Laboratorio de Competencias Digitales 3 ya puede avisarte por aqui.")
        print("Mensaje enviado. Revisa tu Telegram.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
