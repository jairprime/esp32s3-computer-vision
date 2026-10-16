// Plantilla de credenciales.h. Copiala y completa tus datos:
//   cp credenciales.ejemplo.h credenciales.h
// credenciales.h esta en .gitignore: tus contrasenas no se suben a GitHub.
#pragma once

// Red de la universidad: la placa la usa para salir a internet.
#define WIFI_NOMBRE     "NOMBRE_DE_TU_RED"
#define WIFI_CONTRASENA "CONTRASENA_DE_TU_RED"

// Red propia que crea la placa: el PC se conecta aqui para ver la camara.
// La contrasena debe tener al menos 8 caracteres.
#define AP_NOMBRE       "LAB8-CAMARA"
#define AP_CONTRASENA   "CAMBIA_ESTA_CONTRASENA"

// A donde envia la placa las fotos por internet (modo --recibir del contador).
// Es la direccion que muestra "python contador.py --recibir", terminada en /foto.
// Vacio ("") = la placa no envia nada; solo se pueden pedir por la red propia.
#define SERVIDOR_URL    ""
// Debe ser igual a la "clave" de receptor.json. Generala con: openssl rand -hex 16
#define CAMARA_CLAVE    "GENERA_UNA_CLAVE"
