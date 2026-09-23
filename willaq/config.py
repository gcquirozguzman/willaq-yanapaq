"""
Configuración del proyecto.

Aquí se definen las rutas de las carpetas locales (perfil de navegador,
Excel generados) y la URL fija del Blackboard de Cibertec (es la misma
para todos los docentes).

No hay datos personales del profesor configurados a mano: el nombre y la
foto se detectan automáticamente al hacer login (ver willaq/autenticacion/login.py).
"""

import os
from pathlib import Path

# Carpeta raíz del proyecto (dos niveles arriba de este archivo: willaq/config.py -> raíz)
DIR_BASE = Path(__file__).resolve().parent.parent

# URL del Blackboard de Cibertec. Es fija porque es la misma institución
# para todos los profesores que usan esta herramienta.
URL_BLACKBOARD = "https://cibertec.blackboard.com/"

# Portal de Gestión Docente de Cibertec. Es un sistema aparte de Blackboard,
# con su propio login (usuario y contraseña, sin código SMS) y su propia
# sesión, que caduca bastante más seguido que la de Blackboard.
URL_GESTION_DOCENTE = "https://gestiondocente.cibertec.edu.pe/"

# Pantalla de Gestión Docente donde se registran las notas de un curso.
URL_GESTION_DOCENTE_REGISTRO_NOTAS = URL_GESTION_DOCENTE + "Academico/Secure/RegNotas.aspx"

# Carpeta donde se guarda el perfil de navegador (cookies, sesión iniciada).
# Es información sensible y personal de cada profesor: nunca se sube al repo.
DIR_DATOS = DIR_BASE / "datos"
DIR_PERFIL_NAVEGADOR = DIR_DATOS / "perfil_navegador"

# Gestión Docente no tiene perfil de navegador propio a propósito: su
# sesión no sobrevive a cerrar el navegador (ver
# willaq/autenticacion/gestion_docente.py), así que la herramienta entra
# con un navegador limpio cada vez, usando el usuario y la contraseña
# guardados en datos/credenciales_gestion_docente.json.

# Carpeta donde se guardan los archivos Excel generados (plantillas de anuncios, etc.)
DIR_PLANTILLAS = DIR_BASE / "plantillas_generadas"


def _leer_variable_de_env(nombre: str):
    """Lee una variable de un archivo .env en la raíz del proyecto.

    Sin depender de ninguna librería externa (por ahora solo hace falta
    esta variable): si ya existe de verdad en el entorno del sistema
    operativo, se respeta esa; si no, se busca en .env. Devuelve None si
    no está en ningún lado.
    """
    if nombre in os.environ:
        return os.environ[nombre]
    ruta_env = DIR_BASE / ".env"
    if not ruta_env.exists():
        return None
    try:
        for linea in ruta_env.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            if clave.strip() == nombre:
                return valor.strip().strip('"').strip("'")
    except Exception:
        pass
    return None


# Una sola variable (en .env, ver .env.example) que activa o desactiva la
# ventana visible del navegador en TODAS las herramientas que normalmente
# corren sin ella (Obtener Cursos, Generar/Eliminar Anuncios, Generar
# Sesiones Dictado, Obtener Notas, probar credenciales de Gestión
# Docente): sirve para depurar, ver a dónde navega o revisar el HTML real
# de una pantalla, sin tener que tocar el código.
#
# NO afecta el login de Blackboard (el SMS/código de verificación) ni el
# paso del token en "Procesar Notas Gestión Docente": esos SIEMPRE
# muestran la ventana, porque el profesor tiene que escribir algo ahí a
# mano sin importar esta variable.
MOSTRAR_NAVEGADOR = (_leer_variable_de_env("MOSTRAR_NAVEGADOR") or "").strip().lower() in (
    "1",
    "true",
    "verdadero",
    "si",
    "sí",
)
