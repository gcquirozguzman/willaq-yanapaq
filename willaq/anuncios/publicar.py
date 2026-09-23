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

import re

from playwright.sync_api import sync_playwright

from willaq.autenticacion.login import (
    DIR_PERFIL_NAVEGADOR,
    URL_BLACKBOARD,
    _esperar_carga_de_pagina,
    _hacer_clic_en_boton_ingreso,
    _parece_pantalla_de_login,
)
from willaq.config import MOSTRAR_NAVEGADOR

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

# Selectores de la lista de anuncios ya publicados y de su flujo de borrado,
# confirmados navegando de verdad (no inventados). Cada fila trae un botón
# "Más opciones" (el menú de los tres puntos), ese menú trae "Editar",
# "Copiar" y "Eliminar" (cada uno con su propio data-analytics-id), y
# "Eliminar" abre un diálogo de confirmación aparte (de Fluent UI, por eso
# no tiene role="dialog" como el resto del panel) con un botón "Eliminar"
# propio que hay que confirmar; sin ese clic, el anuncio NO se borra.
SELECTOR_FILA_ANUNCIO = "tr.announcement-item-row"
SELECTOR_BOTON_OPCIONES_ANUNCIO = 'button[data-analytics-id="course.announcements.listPanel.listItem.actionMenu"]'
SELECTOR_OPCION_ELIMINAR = 'li[data-analytics-id="course.announcements.listPanel.listItem.delete.button"]'
SELECTOR_BOTON_CONFIRMAR_ELIMINAR = (
    'button[data-analytics-id="course.announcements.listPanel.listItem.deleteDialog.confirm.button"]'
)


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


SELECTOR_ESTADO_LISTA_ANUNCIOS = 'span[role="status"].sr-only'


def _total_anuncios_reportado(pagina):
    """Lee 'Se muestran X anuncios de un total de Y...' y devuelve Y.

    La lista de anuncios es virtualizada: solo renderiza de a 10 filas
    (confirmado con el HTML real: "Se muestran 10 anuncios de un total de
    28..."), así que contar 'tr.announcement-item-row' solo dice cuántas
    hay CARGADAS, no cuántas hay en total. Devuelve None si no se encontró
    ese texto (por ejemplo, si ya no queda ningún anuncio).
    """
    estado = pagina.locator(SELECTOR_ESTADO_LISTA_ANUNCIOS)
    if estado.count() == 0:
        return None
    coincidencia = re.search(r"total de (\d+)", estado.first.inner_text())
    return int(coincidencia.group(1)) if coincidencia else None


def _eliminar_un_anuncio(pagina, notificar) -> bool:
    """Elimina el PRIMER anuncio de la lista actual (la fila de más arriba).

    Devuelve True si la fila desapareció después de intentarlo, False si
    algo no salió como se esperaba (no se pudo abrir el menú, no apareció
    'Eliminar', el diálogo de confirmación no apareció, la fila seguía ahí
    después, o algo inesperado del navegador interrumpió el intento).
    """
    filas = pagina.locator(SELECTOR_FILA_ANUNCIO)
    total_antes = filas.count()
    if total_antes == 0:
        return False
    total_reportado_antes = _total_anuncios_reportado(pagina)

    titulo = "(sin título)"
    try:
        titulo = filas.first.locator(".list-item-title").inner_text() or titulo

        filas.first.locator(SELECTOR_BOTON_OPCIONES_ANUNCIO).click()

        menu = pagina.locator('ul[role="menu"]')
        menu.wait_for(timeout=5_000)

        opcion_eliminar = pagina.locator(SELECTOR_OPCION_ELIMINAR)
        opcion_eliminar.wait_for(timeout=5_000)
        opcion_eliminar.click()

        # Espera a que el menú se cierre del todo antes de seguir: si el
        # siguiente anuncio se intenta borrar mientras este menú sigue
        # abierto (o animándose), Playwright rechaza el clic porque el menú
        # tapa el botón de opciones de la fila.
        try:
            menu.wait_for(state="hidden", timeout=5_000)
        except Exception:
            pass

        # 'Eliminar' del menú SIEMPRE abre un diálogo de confirmación aparte
        # (confirmado navegando de verdad: "¿Eliminar anuncio? ¿Confirma que
        # desea eliminar de forma permanente este anuncio?"); sin este clic
        # el anuncio NO se borra, así que no es opcional como el resto de
        # las esperas de este flujo.
        boton_confirmar = pagina.locator(SELECTOR_BOTON_CONFIRMAR_ELIMINAR)
        boton_confirmar.wait_for(timeout=5_000)
        boton_confirmar.click()

        pagina.wait_for_timeout(1_000)
    except Exception as error:
        notificar(f"[AVISO] No se pudo eliminar '{titulo}' ({error}); se detiene el borrado.")
        return False

    # La lista es virtualizada: al borrar una fila, Blackboard suele
    # rellenar el hueco con la siguiente que tenía cargada, así que contar
    # filas renderizadas ('tr.announcement-item-row') NO alcanza para saber
    # si de verdad se borró (se confirmó navegando de verdad: 10 filas
    # antes, 10 filas después, pero el total real bajó de 27 a 26). Por eso
    # se compara el total reportado por Blackboard ("Se muestran X de un
    # total de Y"); el conteo de filas queda solo como respaldo para
    # cuando ese texto no está (por ejemplo, en el último anuncio).
    total_reportado_despues = _total_anuncios_reportado(pagina)
    if total_reportado_antes is not None and total_reportado_despues is not None:
        elimino_de_verdad = total_reportado_despues < total_reportado_antes
    else:
        elimino_de_verdad = pagina.locator(SELECTOR_FILA_ANUNCIO).count() < total_antes

    if not elimino_de_verdad:
        notificar(f"[AVISO] '{titulo}' no parece haberse eliminado; se detiene el borrado.")
        return False

    notificar(f"[OK] Eliminado: {titulo}")
    return True


def _eliminar_anuncios_existentes(pagina, notificar) -> int:
    """Elimina TODOS los anuncios ya publicados en el curso, uno por uno.

    Blackboard no ofrece un 'eliminar todos' de una sola vez, y la lista es
    virtualizada (solo trae 10 filas cargadas a la vez); por eso, cuando ya
    no queda ninguna fila cargada pero el contador todavía reporta más
    anuncios en total, se hace scroll dentro de la lista para que cargue el
    siguiente lote. Con un tope de intentos (el total reportado por
    Blackboard) para no arriesgar un bucle sin fin si algo deja de
    funcionar como se espera.
    """
    tope = _total_anuncios_reportado(pagina)
    if tope is None:
        tope = pagina.locator(SELECTOR_FILA_ANUNCIO).count()
    if tope == 0:
        return 0

    notificar(f"Eliminando los {tope} anuncio(s) que ya existían en el curso...")
    eliminados = 0
    for _ in range(tope):
        if pagina.locator(SELECTOR_FILA_ANUNCIO).count() == 0:
            restantes = _total_anuncios_reportado(pagina)
            if not restantes:
                break
            # La lista virtualizada no siempre carga sola el siguiente
            # lote: se desplaza el mouse sobre ella para que Blackboard lo
            # traiga (igual que haría el docente al hacer scroll a mano).
            pagina.mouse.wheel(0, 2000)
            pagina.wait_for_timeout(1_500)
            if pagina.locator(SELECTOR_FILA_ANUNCIO).count() == 0:
                notificar(
                    "[AVISO] Quedan anuncios por eliminar, pero la lista no cargó más filas al "
                    "hacer scroll; se detiene el borrado."
                )
                break

        if not _eliminar_un_anuncio(pagina, notificar):
            break
        eliminados += 1

    return eliminados


def generar_anuncios_en_blackboard(
    id_curso: str, anuncios: list, eliminar_existentes: bool = False, notificar=None
) -> dict:
    """Publica una lista de anuncios ya armados como anuncios reales de Blackboard.

    'id_curso' es el ID interno de Blackboard del curso (ver
    willaq/cursos/listar.py). 'anuncios' es una lista de diccionarios con
    "titulo", "mensaje", "fecha" (YYYY-MM-DD) y "hora" (HH:MM, 24 horas),
    tal como se ven en la grilla "Ver anuncios" del panel: se publica
    exactamente lo que el docente vio y pudo editar ahí. Si
    'eliminar_existentes' es True, antes de crear los nuevos se borran TODOS
    los anuncios que ya existan en el curso (ver _eliminar_anuncios_existentes).

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
        # Sin ventana visible por defecto: esto no necesita ninguna acción
        # manual del docente. MOSTRAR_NAVEGADOR (ver willaq/config.py,
        # variable de .env) la muestra igual, para depurar.
        contexto = playwright.chromium.launch_persistent_context(
            user_data_dir=str(DIR_PERFIL_NAVEGADOR),
            headless=not MOSTRAR_NAVEGADOR,
        )
        pagina = contexto.pages[0] if contexto.pages else contexto.new_page()
        # wait_until="domcontentloaded" (no el "load" por defecto): Blackboard
        # mantiene conexiones de red abiertas de fondo y a veces tarda más de
        # 30s en llegar a "load" (confirmado navegando de verdad: ~26s, al
        # borde del timeout por defecto), aunque el DOM ya está listo mucho
        # antes. Mismo patrón que willaq/autenticacion/gestion_docente.py y
        # willaq/notas/recursos.py.
        pagina.goto(URL_BLACKBOARD, wait_until="domcontentloaded", timeout=60_000)
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

        pagina.goto(
            f"{URL_BLACKBOARD}ultra/courses/{id_curso}/announcements",
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        _esperar_carga_de_pagina(pagina)

        try:
            # 45s y no 15s a propósito: en un curso SIN anuncios todavía,
            # Blackboard muestra un estado vacío distinto (panel "Anuncie
            # algo a su clase") que tarda bastante más en aparecer que
            # cuando ya hay anuncios. Además, en ese estado vacío Blackboard
            # renderiza DOS botones con el mismo data-analytics-id a la vez
            # (el ícono de la barra superior + el botón grande dentro del
            # panel "Anuncie algo a su clase"); confirmado navegando de
            # verdad, por eso se usa '.first' aquí y en el clic más abajo
            # (cualquiera de los dos abre el mismo panel "Crear anuncio").
            pagina.locator(SELECTOR_BOTON_CREAR_ANUNCIO).first.wait_for(timeout=45_000)
        except Exception:
            # Se incluye la URL a la que se llegó (no solo "no se encontró"),
            # porque esto puede pasar por varios motivos bien distintos: un
            # id_curso vencido/incorrecto, un curso sin el tablero de
            # anuncios habilitado, o que la página tardó más de la cuenta en
            # cargar. La URL ayuda a distinguirlos sin tener que repetir la
            # prueba a ciegas.
            url_actual = pagina.url
            contexto.close()
            return {
                "estado": "error",
                "error": f"No se encontró la página de anuncios del curso. URL: {url_actual}",
                "publicados": 0,
                "fallidos": [],
            }

        if eliminar_existentes:
            eliminados = _eliminar_anuncios_existentes(pagina, notificar)
            notificar(f"[OK] Se eliminaron {eliminados} anuncio(s) existente(s).")

        for anuncio in anuncios:
            notificar(f"Creando anuncio: {anuncio['titulo']}...")
            try:
                pagina.locator(SELECTOR_BOTON_CREAR_ANUNCIO).first.click()
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
