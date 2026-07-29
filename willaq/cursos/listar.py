"""
Obtiene la lista de cursos activos (abiertos) del docente en Blackboard.

Reutiliza el mismo perfil de navegador persistente que 'login' (así no hace
falta volver a iniciar sesión si ya hay una sesión guardada): abre el
navegador, entra a la página principal de Blackboard igual que el login, y
desde ahí navega a https://cibertec.blackboard.com/ultra/course, donde
Blackboard muestra una tarjeta por cada curso del docente.

Un curso se considera "activo" si su tarjeta muestra el estado "Abierto"
(en el HTML: bb-translate="base.courses.open"). Los cursos finalizados
muestran bb-translate="base.courses.closed" en su lugar y se descartan.
Todo esto se confirmó con el HTML real de la página.
"""

import json

from playwright.sync_api import sync_playwright

from willaq.autenticacion.login import (
    DIR_PERFIL_NAVEGADOR,
    URL_BLACKBOARD,
    _esperar_carga_de_pagina,
    _hacer_clic_en_boton_ingreso,
    _parece_pantalla_de_login,
)
from willaq.config import DIR_DATOS

URL_CURSOS = URL_BLACKBOARD + "ultra/course"

# Caché del último resultado exitoso de "Obtener Cursos Activos", para que el
# panel web pueda seguir mostrando la lista tras reiniciar el servidor, sin
# obligar al docente a volver a pedirla solo por eso. Se sobrescribe cada vez
# que se vuelve a obtener la lista (por ejemplo, si un curso cambia de estado).
RUTA_CURSOS_GUARDADOS = DIR_DATOS / "cursos_activos.json"


def _guardar_cursos_obtenidos(cursos: list):
    try:
        DIR_DATOS.mkdir(parents=True, exist_ok=True)
        RUTA_CURSOS_GUARDADOS.write_text(json.dumps(cursos), encoding="utf-8")
    except Exception:
        pass  # esto es solo una comodidad de la interfaz; si falla, no afecta la búsqueda


def cargar_cursos_guardados():
    """Lee la última lista de cursos activos guardada en disco, si existe.

    Devuelve None si nunca se guardó nada (por ejemplo, primera vez que se
    usa la herramienta).
    """
    try:
        if RUTA_CURSOS_GUARDADOS.exists():
            return json.loads(RUTA_CURSOS_GUARDADOS.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None

# Selectores confirmados con el HTML real de la página de cursos.
SELECTOR_TARJETA_CURSO = "article[data-course-id]"
SELECTOR_CODIGO_CURSO = ".course-id span"
SELECTOR_NOMBRE_CURSO = "h4.js-course-title-element"
SELECTOR_ESTADO_ABIERTO = 'span[bb-translate="base.courses.open"]'


def _extraer_cursos_activos(pagina, notificar) -> list:
    """Lee las tarjetas de curso de la página y devuelve solo los activos."""
    cursos = []

    try:
        pagina.locator(SELECTOR_TARJETA_CURSO).first.wait_for(timeout=15_000)
    except Exception as error:
        notificar(f"[AVISO] No se pudo cargar la lista de cursos: {error}")
        return cursos

    tarjetas = pagina.locator(SELECTOR_TARJETA_CURSO)
    for indice in range(tarjetas.count()):
        tarjeta = tarjetas.nth(indice)
        try:
            if tarjeta.locator(SELECTOR_ESTADO_ABIERTO).count() == 0:
                continue  # no dice "Abierto" (está finalizado, etc.): se descarta
            codigo = tarjeta.locator(SELECTOR_CODIGO_CURSO).inner_text(timeout=2_000).strip()
            nombre = tarjeta.locator(SELECTOR_NOMBRE_CURSO).inner_text(timeout=2_000).strip()
            cursos.append({"codigo": codigo, "nombre": nombre})
        except Exception:
            continue  # si una tarjeta puntual falla al leerse, seguimos con las demás

    return cursos


def obtener_cursos_activos(notificar=None) -> list:
    """Abre el navegador, va a la lista de cursos y devuelve los activos.

    Requiere que ya exista una sesión guardada (ejecutar 'login' antes). Si
    no hay sesión activa, avisa por qué y devuelve una lista vacía.
    """
    notificar = notificar or print

    notificar("Buscando tus cursos activos en Blackboard...")

    with sync_playwright() as playwright:
        # Mismo patrón que el login: perfil persistente, navegador visible.
        contexto = playwright.chromium.launch_persistent_context(
            user_data_dir=str(DIR_PERFIL_NAVEGADOR),
            headless=False,
        )

        pagina = contexto.pages[0] if contexto.pages else contexto.new_page()
        pagina.goto(URL_BLACKBOARD)
        _esperar_carga_de_pagina(pagina)

        _hacer_clic_en_boton_ingreso(pagina, notificar)
        _esperar_carga_de_pagina(pagina)

        if _parece_pantalla_de_login(pagina.url):
            notificar("[AVISO] No hay una sesión activa. Primero inicia sesión con 'Iniciar sesión'.")
            contexto.close()
            return []

        pagina.goto(URL_CURSOS)
        _esperar_carga_de_pagina(pagina)

        cursos = _extraer_cursos_activos(pagina, notificar)
        notificar(f"Se encontraron {len(cursos)} curso(s) activo(s).")
        _guardar_cursos_obtenidos(cursos)

        contexto.close()

    return cursos


def obtener_cursos_activos_cli():
    """Versión para la terminal: imprime la lista de cursos encontrados."""
    cursos = obtener_cursos_activos()

    if not cursos:
        return

    print("=" * 70)
    print(f"[OK] {len(cursos)} curso(s) activo(s):")
    for curso in cursos:
        print(f"  - {curso['codigo']}: {curso['nombre']}")
    print("=" * 70)
