"""
Publicación automática de anuncios en Blackboard, usando el panel real
'Crear anuncio' de cada curso.

Cómo funciona (confirmado navegando de verdad con la sesión guardada; los
selectores de abajo salen del HTML real del panel, no están inventados):

1. Entra al curso usando su ID interno de Blackboard (el mismo que aparece
   en el atributo 'data-course-id' de la tarjeta del curso en la lista de
   cursos; ver willaq/cursos/listar.py), navegando directo a
   https://cibertec.blackboard.com/ultra/courses/<id>/announcements. La
   navegación por clic en la tarjeta de la lista no sirve aquí: ese link
   solo cambia el estado interno de Angular sin actualizar la URL, así que
   toca ir directo con esta URL ya confirmada.
2. Por cada anuncio, hace clic en 'Crear anuncio', llena el título y el
   mensaje, marca 'Programar anuncio' (lo que revela los campos de fecha y
   hora de publicación, precargados por Blackboard con la fecha/hora
   actual), y reemplaza esos dos campos con la fecha/hora indicada.
3. Hace clic en 'Publicar'.

Los campos de fecha y hora son inputs de texto (no <input type="date">).
Probado con varios formatos: el de fecha acepta 'YYYY-MM-DD' (se
autoformatea), pero un formato ambiguo tipo 'MM/DD/YYYY' lo deja inválido y
el botón 'Publicar' se queda deshabilitado; por eso se usa 'YYYY-MM-DD'
siempre. El de hora acepta 'HH:MM' en 24 horas sin problema.
"""

from playwright.sync_api import sync_playwright

from willaq.autenticacion.login import (
    DIR_PERFIL_NAVEGADOR,
    URL_BLACKBOARD,
    _esperar_carga_de_pagina,
    _hacer_clic_en_boton_ingreso,
    _parece_pantalla_de_login,
)

# Selectores confirmados con el HTML real del panel "Crear anuncio" de
# Blackboard (dados por el usuario o descubiertos navegando con la sesión
# real; no inventados).
SELECTOR_BOTON_CREAR_ANUNCIO = 'button[data-analytics-id="course.announcements.listPanel.create.button"]'
SELECTOR_CAMPO_TITULO = 'input[data-analytics-id="course.announcements.detailPanel.title.input.text"]'
SELECTOR_EDITOR_MENSAJE = "#bb-editor-textbox"
SELECTOR_CASILLA_PROGRAMAR = "#schedule-announcement-checkbox"
SELECTOR_CAMPO_FECHA = (
    'div[data-analytics-id="course.announcements.detailPanel.showOn.datePicker.input.text"] input.date-input'
)
SELECTOR_CAMPO_HORA = 'input[data-analytics-id="course.announcements.detailPanel.showOn.timePicker.input.text"]'
SELECTOR_BOTON_PUBLICAR = 'button[data-analytics-id="course.announcements.detailPanel.post.button"]'
SELECTOR_BOTON_CANCELAR = 'button[data-analytics-id="course.announcements.detailPanel.cancel.button"]'


def _crear_un_anuncio(pagina, anuncio, notificar) -> bool:
    """Llena y publica un único anuncio en el panel 'Crear anuncio', ya abierto.

    Devuelve True si se pudo publicar, False si el formulario quedó
    inválido (por ejemplo, una fecha con formato raro) y hubo que cancelar.
    """
    pagina.locator(SELECTOR_CAMPO_TITULO).fill(anuncio["titulo"])

    editor = pagina.locator(SELECTOR_EDITOR_MENSAJE)
    editor.click()
    editor.type(anuncio["mensaje"])

    pagina.locator(SELECTOR_CASILLA_PROGRAMAR).check()
    pagina.wait_for_timeout(500)

    campo_fecha = pagina.locator(SELECTOR_CAMPO_FECHA)
    campo_fecha.fill(anuncio["fecha"])
    campo_fecha.press("Tab")

    campo_hora = pagina.locator(SELECTOR_CAMPO_HORA)
    campo_hora.fill(anuncio["hora"])
    campo_hora.press("Tab")

    pagina.wait_for_timeout(500)

    boton_publicar = pagina.locator(SELECTOR_BOTON_PUBLICAR)
    if boton_publicar.is_disabled():
        notificar(f"[AVISO] El formulario quedó inválido para '{anuncio['titulo']}'; se cancela ese anuncio.")
        pagina.locator(SELECTOR_BOTON_CANCELAR).click()
        pagina.wait_for_timeout(500)
        return False

    boton_publicar.click()
    pagina.wait_for_timeout(2_000)
    return True


def generar_anuncios_en_blackboard(id_curso: str, anuncios: list, notificar=None) -> dict:
    """Publica una lista de anuncios ya armados como anuncios reales de Blackboard.

    'id_curso' es el ID interno de Blackboard del curso (ver
    willaq/cursos/listar.py). 'anuncios' es una lista de diccionarios con
    "titulo", "mensaje", "fecha" (YYYY-MM-DD) y "hora" (HH:MM, 24 horas),
    tal como se ven en la grilla "Ver anuncios" del panel: se publica
    exactamente lo que el docente vio y pudo editar ahí.

    Devuelve {"estado": "ok"|"parcial"|"error", "publicados": N,
    "fallidos": [...], "error": "..."}.
    """
    notificar = notificar or print

    if not id_curso:
        return {"estado": "error", "error": "No se pudo identificar el curso en Blackboard.", "publicados": 0, "fallidos": []}
    if not anuncios:
        return {"estado": "error", "error": "No hay anuncios para publicar.", "publicados": 0, "fallidos": []}

    publicados = 0
    fallidos = []

    with sync_playwright() as playwright:
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
            contexto.close()
            return {
                "estado": "error",
                "error": "No hay una sesión activa. Inicia sesión primero.",
                "publicados": 0,
                "fallidos": [],
            }

        pagina.goto(f"{URL_BLACKBOARD}ultra/courses/{id_curso}/announcements")
        _esperar_carga_de_pagina(pagina)

        try:
            pagina.locator(SELECTOR_BOTON_CREAR_ANUNCIO).wait_for(timeout=15_000)
        except Exception:
            contexto.close()
            return {
                "estado": "error",
                "error": "No se encontró la página de anuncios del curso.",
                "publicados": 0,
                "fallidos": [],
            }

        for anuncio in anuncios:
            notificar(f"Creando anuncio: {anuncio['titulo']}...")
            try:
                pagina.locator(SELECTOR_BOTON_CREAR_ANUNCIO).click()
                pagina.wait_for_timeout(1_500)
                if _crear_un_anuncio(pagina, anuncio, notificar):
                    publicados += 1
                    notificar(f"[OK] Publicado: {anuncio['titulo']}")
                else:
                    fallidos.append(anuncio["titulo"])
            except Exception as error:
                notificar(f"[ERROR] No se pudo crear '{anuncio['titulo']}': {error}")
                fallidos.append(anuncio["titulo"])

        contexto.close()

    estado = "ok" if not fallidos else ("parcial" if publicados else "error")
    return {"estado": estado, "publicados": publicados, "fallidos": fallidos}
