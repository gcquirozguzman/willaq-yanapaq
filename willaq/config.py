"""
Configuración del proyecto.

Aquí se definen las rutas de las carpetas locales (perfil de navegador,
Excel generados) y la URL fija del Blackboard de Cibertec (es la misma
para todos los docentes).

No hay datos personales del profesor configurados a mano: el nombre y la
foto se detectan automáticamente al hacer login (ver willaq/autenticacion/login.py).
"""

from pathlib import Path

# Carpeta raíz del proyecto (dos niveles arriba de este archivo: willaq/config.py -> raíz)
DIR_BASE = Path(__file__).resolve().parent.parent

# URL del Blackboard de Cibertec. Es fija porque es la misma institución
# para todos los profesores que usan esta herramienta.
URL_BLACKBOARD = "https://cibertec.blackboard.com/"

# Carpeta donde se guarda el perfil de navegador (cookies, sesión iniciada).
# Es información sensible y personal de cada profesor: nunca se sube al repo.
DIR_DATOS = DIR_BASE / "datos"
DIR_PERFIL_NAVEGADOR = DIR_DATOS / "perfil_navegador"

# Carpeta donde se guardan los archivos Excel generados (plantillas de anuncios, etc.)
DIR_PLANTILLAS = DIR_BASE / "plantillas_generadas"
