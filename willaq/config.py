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
