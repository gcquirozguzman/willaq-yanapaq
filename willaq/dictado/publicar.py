"""
Publicación automática de las sesiones de dictado como sesiones reales de
Blackboard Collaborate (NO como anuncios: son cosas distintas dentro de
Blackboard).

Cómo funciona (confirmado navegando de verdad con la sesión guardada; los
selectores de abajo salen del HTML real, no están inventados):

1. Entra a la página de contenido del curso
   (https://cibertec.blackboard.com/ultra/courses/<id>/outline).
2. Junto a "Class Collaborate" hay un botón de opciones ("⋯"). Al hacer
   clic se abre un menú; se elige "Administrar todas las sesiones", lo que
   cambia la URL del curso a ".../outline/collab/launchSessions" y carga
   ahí mismo un iframe de otro dominio (us-lti.bbcollab.com) con la lista
   de sesiones de Collaborate del curso.
3. Dentro de ese iframe, el botón "Crear sesión" (id="page-add-course-button")
   abre el formulario de una sesión nueva en ese mismo iframe (URL termina
   en "/session/new"). Ese botón sufre un problema de solapamiento visual
   con otro elemento de la lista (parece un bug de la propia página de
   Collaborate, reproducible siempre): un clic normal de Playwright falla
   porque otro elemento "intercepta" el punto donde se hace clic, así que
   se dispara un click() de DOM directamente sobre el botón en vez de un
   clic por coordenadas.
4. En el formulario: nombre (id="session-name") y fecha/hora de inicio
   (name="startDate"/"startTime") y de fin (name="endDate"/"endTime"). No
   se llena la descripción (el campo arranca oculto y no hace falta). Los
   campos de fecha esperan el formato "D/M/AA" (día y mes sin cero a la
   izquierda, año de 2 dígitos: confirmado escribiendo "6/8/26" y viendo
   que el campo queda con la clase "ng-valid-date" sin ningún
   "ng-invalid"). Los de hora esperan "HH:MM" en 24 horas (confirmado con
   "19:00"/"20:30").
5. El botón "Crear" (clase "save-button") queda deshabilitado hasta que el
   formulario es válido; se hace clic ahí para guardar. El mismo problema
   de solapamiento visual del punto 3 aparece también en este botón (y en
   "Cancelar"), así que todos los clics de este módulo se hacen con
   click() de DOM en vez de por coordenadas de pantalla, para no terminar
   haciendo clic en el elemento equivocado.

"Eliminar sesiones no iniciadas" (del panel) NO busca por el nombre que
el panel cree que debería existir: entra a la lista real de Collaborate y
elimina las que Blackboard mismo diga que aún no han comenzado. Esto
importa porque una reprogramación puede hacer que el nombre que el panel
calcula hoy para una fecha ya no coincida con el nombre que tenía la
sesión cuando se creó en Blackboard (la reprogramación reordena y
renumera); guiarse por nombres calculados localmente dejaría sesiones
"huérfanas" sin poder eliminarlas.

Cada fila de la lista de Collaborate muestra su propio estado como texto,
confirmado navegando de verdad:
- Sesión que aún no comienza: "D/M/AA HH:MM – D/M/AA HH:MM (aún no ha
  comenzado)".
- Sesión ya finalizada (visible solo bajo el filtro "Todas las sesiones
  anteriores", ver abajo): "Finalizado: D/M/AA HH:MM".
La fila fija "<curso> - Sala del curso" (la sala persistente del curso,
no una sesión de dictado) se identifica porque su texto contiene "Sala
del curso" y su estado es "Bloqueado"; nunca se toca.

La lista tiene un filtro ("Filtrar por") con tres modos: "Todas las
próximas sesiones" (el que queda activo por defecto cada vez que se
navega de cero a la lista, que es lo que hace este módulo en cada
operación), "Todas las sesiones anteriores" y "Sesiones en el intervalo".
Confirmado navegando de verdad: con el filtro por defecto activo, ni la
lista ni la búsqueda por nombre muestran sesiones "Finalizado". Por eso
basta con no tocar nunca ese filtro para que este módulo, al enumerar las
filas, jamás vea (y por lo tanto jamás pueda eliminar) una sesión ya
finalizada; y filtrando además por el texto "(aún no ha comenzado)" se
excluye toda sesión que ya esté en curso.

Para eliminar una sesión puntual una vez identificado su nombre real: se
busca por ese nombre exacto (con el botón "Buscar sesiones"), se abre su
menú de opciones (id="session-<id>-options-dropdown-toggle") y se hace
clic en "Eliminar sesión" (analytics-id="session.session-list.delete-
session"), lo que abre un modal de confirmación cuyo botón es
id="confirmation-modal-confirm" ("Sí, eliminarla"). Confirmado eliminando
de verdad una sesión de prueba y comprobando que ya no aparecía en la
búsqueda. Como defensa adicional, si la fila encontrada en ese momento
contuviera el texto "Finalizado" se aborta esa eliminación en vez de
continuar.

Por cada sesión se repite el flujo completo desde la página de contenido
del curso (en vez de asumir a qué pantalla se vuelve después de crear o
eliminar una sesión), para no depender de un comportamiento de navegación
posterior que no se pudo confirmar sin operar contra Blackboard real. Al
eliminar en barrido, esto además hace que la lista se vuelva a leer desde
cero después de cada eliminación, así que un cambio en el estado de una
sesión mientras se procesan las demás (por ejemplo, que empiece a dictarse
justo en ese momento) queda reflejado antes de decidir sobre la siguiente.
"""

from playwright.sync_api import sync_playwright

from willaq.autenticacion.login import (
    DIR_PERFIL_NAVEGADOR,
    URL_BLACKBOARD,
    _esperar_carga_de_pagina,
    _hacer_clic_en_boton_ingreso,
    _parece_pantalla_de_login,
)

# Selectores confirmados con el HTML real de Blackboard/Collaborate.
SELECTOR_BOTON_OPCIONES_COLLAB = '[analytics-id="course.outline.collab.overflowMenu.showMenu.button"]'
SELECTOR_ITEM_ADMINISTRAR_SESIONES = (
    '[analytics-id="course.outline.collab.overflowMenu.course.outline.collab.ultraCollabMenu.viewSessionsItem.link"]'
)
SELECTOR_BOTON_CREAR_SESION = "#page-add-course-button"
SELECTOR_CAMPO_NOMBRE_SESION = "#session-name"
SELECTOR_CAMPO_FECHA_INICIO = "input[name='startDate']"
SELECTOR_CAMPO_HORA_INICIO = "input[name='startTime']"
SELECTOR_CAMPO_FECHA_FIN = "input[name='endDate']"
SELECTOR_CAMPO_HORA_FIN = "input[name='endTime']"
SELECTOR_BOTON_CREAR_SUBMIT = "button.save-button"
SELECTOR_BOTON_BUSCAR_SESIONES = 'button[aria-label="Buscar sesiones"]'
SELECTOR_CAMPO_BUSQUEDA_SESIONES = "input[placeholder*='nombre de la sesión']"
SELECTOR_BOTON_ELIMINAR_SESION = '[analytics-id="session.session-list.delete-session"]'
SELECTOR_BOTON_CONFIRMAR_ELIMINAR = "#confirmation-modal-confirm"


def _formatear_fecha_collaborate(fecha_iso: str) -> str:
    """Convierte 'YYYY-MM-DD' al formato 'D/M/AA' que espera Collaborate."""
    anio, mes, dia = fecha_iso.split("-")
    return f"{int(dia)}/{int(mes)}/{anio[2:]}"


def _esperar_frame_collab(pagina, debe_contener: str, timeout_segundos: int = 40):
    """Espera a que aparezca un iframe de bbcollab.com cuya URL contenga 'debe_contener'.

    Revisa cada 250ms (no cada segundo): normalmente el iframe aparece casi
    de inmediato, así que sondear más seguido reduce la espera real sin
    bajar el tope máximo de espera.
    """
    intentos = timeout_segundos * 4
    for _ in range(intentos):
        for frame in pagina.frames:
            if "bbcollab.com" in frame.url and debe_contener in frame.url:
                return frame
        pagina.wait_for_timeout(250)
    return None


def _abrir_lista_de_sesiones(pagina, id_curso: str, notificar):
    """Navega desde cero hasta la lista de sesiones de Collaborate del curso.

    Devuelve el frame de esa lista, o None si no se pudo llegar (avisando
    en qué paso falló, en vez de fallar en silencio).
    """
    pagina.goto(f"{URL_BLACKBOARD}ultra/courses/{id_curso}/outline")
    _esperar_carga_de_pagina(pagina)

    # Sin espera fija antes de estos clics: .click() de Playwright (no el
    # click() de DOM que se usa más abajo, dentro del iframe) ya espera por
    # su cuenta a que el botón esté visible/estable/habilitado, hasta su
    # propio timeout. Una espera fija aparte solo sumaba tiempo muerto.
    try:
        pagina.locator(SELECTOR_BOTON_OPCIONES_COLLAB).click(timeout=15_000)
    except Exception as error:
        notificar(f"[ERROR] No se encontró el botón de opciones de Collaborate: {error}")
        return None

    try:
        pagina.locator(SELECTOR_ITEM_ADMINISTRAR_SESIONES).click(timeout=10_000)
    except Exception as error:
        notificar(f"[ERROR] No se encontró 'Administrar todas las sesiones': {error}")
        return None

    frame_lista = _esperar_frame_collab(pagina, debe_contener="")
    if frame_lista is None:
        notificar("[ERROR] No cargó la lista de sesiones de Collaborate (iframe de bbcollab.com).")
        return None

    # Antes había aquí una espera fija de 6s para dejar que la lista
    # "asiente" antes de hacer clic en su primer botón real, pensada para
    # el problema de solapamiento visual descrito arriba. ya no hace falta:
    # ese problema solo afectaba a los clics por coordenadas, y todos los
    # clics de este módulo usan click() de DOM (ver más abajo), que no le
    # hace hit-testing a nada. Lo que sí sigue haciendo falta es esperar a
    # que el botón en cuestión exista de verdad en el DOM, y eso lo hace
    # cada función que sigue usando wait_for(state="visible") antes de su
    # primer clic, en vez de una espera fija aquí que aplicaba a ciegas a
    # los dos flujos (crear y eliminar) aunque solo uno la necesitara.
    return frame_lista
    return frame_lista


def _crear_una_sesion(pagina, id_curso: str, sesion: dict, notificar) -> bool:
    """Crea una sesión real de Collaborate. Devuelve True si se pudo crear."""
    frame_lista = _abrir_lista_de_sesiones(pagina, id_curso, notificar)
    if frame_lista is None:
        notificar(f"[ERROR] No se pudo abrir la lista de sesiones de Collaborate para '{sesion['titulo']}'.")
        return False

    try:
        boton_crear_sesion = frame_lista.locator(SELECTOR_BOTON_CREAR_SESION)
        boton_crear_sesion.wait_for(state="visible", timeout=15_000)
        boton_crear_sesion.evaluate("el => el.click()")
    except Exception as error:
        notificar(f"[ERROR] No se pudo hacer clic en 'Crear sesión' para '{sesion['titulo']}': {error}")
        return False

    frame_formulario = _esperar_frame_collab(pagina, debe_contener="/session/new", timeout_segundos=20)
    if frame_formulario is None:
        notificar(f"[ERROR] No se abrió el formulario de nueva sesión para '{sesion['titulo']}'.")
        return False

    fecha_collab = _formatear_fecha_collaborate(sesion["fecha"])

    frame_formulario.locator(SELECTOR_CAMPO_NOMBRE_SESION).fill(sesion["titulo"])

    campo_fecha_inicio = frame_formulario.locator(SELECTOR_CAMPO_FECHA_INICIO)
    campo_fecha_inicio.fill(fecha_collab)
    campo_fecha_inicio.press("Tab")

    campo_hora_inicio = frame_formulario.locator(SELECTOR_CAMPO_HORA_INICIO)
    campo_hora_inicio.fill(sesion["hora_inicio"])
    campo_hora_inicio.press("Tab")

    campo_fecha_fin = frame_formulario.locator(SELECTOR_CAMPO_FECHA_FIN)
    campo_fecha_fin.fill(fecha_collab)
    campo_fecha_fin.press("Tab")

    campo_hora_fin = frame_formulario.locator(SELECTOR_CAMPO_HORA_FIN)
    campo_hora_fin.fill(sesion["hora_fin"])
    campo_hora_fin.press("Tab")

    # No se llena la descripción: el campo arranca oculto en el formulario
    # de Collaborate y agregarla no es necesario para el docente.

    # Angular valida los campos de forma asíncrona (bb-date-picker/bb-time-picker):
    # justo después de llenar el último campo, el botón "Crear" puede seguir
    # apareciendo deshabilitado por un instante aunque el formulario ya sea
    # válido. Se reintenta unas cuantas veces en vez de revisarlo una sola vez,
    # para no cancelar por error una sesión que en realidad sí es válida.
    boton_crear = frame_formulario.locator(SELECTOR_BOTON_CREAR_SUBMIT)
    habilitado = False
    for _ in range(10):
        pagina.wait_for_timeout(500)
        if boton_crear.get_attribute("disabled") is None:
            habilitado = True
            break

    if not habilitado:
        notificar(f"[AVISO] El formulario quedó inválido para '{sesion['titulo']}'; se cancela esa sesión.")
        try:
            # click() de DOM en vez de por coordenadas: ver la nota sobre
            # 'Crear sesión' más arriba, el mismo problema de solapamiento
            # visual aparece en los botones de este panel.
            frame_formulario.get_by_role("button", name="Cancelar", exact=True).evaluate("el => el.click()")
        except Exception:
            pass
        return False

    # click() de DOM en vez de por coordenadas: un clic normal (incluso con
    # force=True, que solo salta las validaciones de Playwright pero sigue
    # apuntando por coordenadas de pantalla) puede terminar cayendo sobre
    # otro elemento que visualmente tapa a este botón, en vez del botón
    # "Crear" en sí. Mismo problema y misma solución que con "Crear sesión".
    boton_crear.evaluate("el => el.click()")
    # Espera a que el guardado se refleje de verdad (que el formulario
    # "/session/new" haya desaparecido) antes de seguir, en vez de siempre
    # asumir lo peor con una espera fija larga.
    for _ in range(12):
        sigue_en_formulario = any(
            "bbcollab.com" in frame.url and "/session/new" in frame.url for frame in pagina.frames
        )
        if not sigue_en_formulario:
            break
        pagina.wait_for_timeout(250)
    pagina.wait_for_timeout(800)
    return True


def _listar_titulos_no_iniciados(frame_lista) -> list:
    """Devuelve los nombres de las filas que Blackboard marca como
    "(aún no ha comenzado)", tal como aparecen en la lista de Collaborate
    con el filtro por defecto ("Todas las próximas sesiones") activo.

    Excluye la fila fija "<curso> - Sala del curso" (no es una sesión de
    dictado, es la sala persistente del curso).
    """
    titulos = []
    filas = frame_lista.locator("button.session-list-item-content")
    for indice in range(filas.count()):
        texto = filas.nth(indice).inner_text()
        if "Sala del curso" in texto:
            continue
        if "(aún no ha comenzado)" not in texto:
            continue
        titulos.append(texto.split("\n")[0].strip())
    return titulos


def _eliminar_una_sesion(pagina, frame_lista, titulo: str, notificar) -> bool:
    """Elimina, si existe, la sesión de Collaborate con ese nombre exacto.

    Recibe 'frame_lista' ya abierto (lo abre y lo relee quien llama, para
    decidir qué queda pendiente) en vez de volver a abrirlo aquí: abrir la
    lista es lo más lento de todo el flujo, así que hacerlo dos veces por
    cada eliminación (una para ver qué falta, otra para eliminarla) le
    duplicaba el tiempo a esta acción sin necesidad.
    """
    try:
        boton_buscar = frame_lista.locator(SELECTOR_BOTON_BUSCAR_SESIONES)
        boton_buscar.wait_for(state="visible", timeout=15_000)
        boton_buscar.evaluate("el => el.click()")
        frame_lista.locator(SELECTOR_CAMPO_BUSQUEDA_SESIONES).fill(titulo)
    except Exception as error:
        notificar(f"[ERROR] No se pudo buscar '{titulo}': {error}")
        return False

    # La lista filtra en vivo mientras se escribe; se sondea seguido en vez
    # de una espera fija, para seguir en cuanto aparezca el resultado.
    fila_titulo = frame_lista.get_by_text(titulo, exact=True)
    for _ in range(16):
        if fila_titulo.count() > 0:
            break
        pagina.wait_for_timeout(250)

    if fila_titulo.count() == 0:
        notificar(f"[AVISO] No se encontró entre las sesiones no iniciadas la sesión '{titulo}' (puede que ya no exista, ya haya comenzado, o ya haya finalizado).")
        return False

    try:
        boton_fila = fila_titulo.first.locator(
            "xpath=ancestor::button[contains(@class,'session-list-item-content')][1]"
        )
        # Defensa adicional: aunque la búsqueda ya se hace con el filtro
        # "Todas las próximas sesiones" activo (que nunca incluye sesiones
        # finalizadas, confirmado navegando de verdad), si por algún motivo
        # la fila encontrada igual mostrara "Finalizado" se aborta en vez
        # de eliminarla.
        if "Finalizado" in boton_fila.inner_text():
            notificar(f"[AVISO] '{titulo}' ya finalizó en Blackboard; no se elimina.")
            return False
        id_sesion = boton_fila.get_attribute("id").replace("session-", "")

        boton_opciones = frame_lista.locator(f"#session-{id_sesion}-options-dropdown-toggle")
        boton_opciones.wait_for(state="visible", timeout=10_000)
        boton_opciones.evaluate("el => el.click()")

        boton_eliminar = frame_lista.locator(SELECTOR_BOTON_ELIMINAR_SESION)
        boton_eliminar.wait_for(state="visible", timeout=10_000)
        boton_eliminar.evaluate("el => el.click()")

        boton_confirmar = frame_lista.locator(SELECTOR_BOTON_CONFIRMAR_ELIMINAR)
        boton_confirmar.wait_for(state="visible", timeout=10_000)
        boton_confirmar.evaluate("el => el.click()")

        # Espera a que el borrado se refleje de verdad (que la fila haya
        # desaparecido) antes de seguir, en vez de siempre asumir lo peor
        # con una espera fija larga.
        for _ in range(12):
            if fila_titulo.count() == 0:
                break
            pagina.wait_for_timeout(250)
        pagina.wait_for_timeout(500)
    except Exception as error:
        notificar(f"[ERROR] No se pudo eliminar '{titulo}': {error}")
        return False

    return True


def _iniciar_sesion_blackboard(playwright, notificar):
    """Abre el navegador con la sesión guardada y navega a Blackboard ya logueado.

    Devuelve (contexto, pagina), o (contexto, None) si no hay sesión activa
    (el contexto ya viene cerrado en ese caso, para no dejarlo colgado).

    Sin ventana visible: esto no necesita ninguna acción manual del docente
    (a diferencia del login, que sí la necesita).
    """
    contexto = playwright.chromium.launch_persistent_context(
        user_data_dir=str(DIR_PERFIL_NAVEGADOR),
        headless=True,
    )
    pagina = contexto.pages[0] if contexto.pages else contexto.new_page()
    pagina.goto(URL_BLACKBOARD)
    _esperar_carga_de_pagina(pagina)
    _hacer_clic_en_boton_ingreso(pagina, notificar)
    _esperar_carga_de_pagina(pagina)

    if _parece_pantalla_de_login(pagina.url):
        contexto.close()
        return contexto, None

    return contexto, pagina


def generar_sesiones_en_blackboard(id_curso: str, sesiones: list, notificar=None) -> dict:
    """Publica una lista de sesiones de dictado como sesiones reales de Collaborate.

    'sesiones' es una lista de diccionarios con "titulo", "fecha"
    (YYYY-MM-DD), "hora_inicio" y "hora_fin" (HH:MM, 24 horas), tal como
    se ven en la grilla "Ver Sesiones" del panel.

    Devuelve {"estado": "ok"|"parcial"|"error", "publicados": N,
    "fallidos": [...], "error": "..."}.
    """
    notificar = notificar or print

    if not id_curso:
        return {"estado": "error", "error": "No se pudo identificar el curso en Blackboard.", "publicados": 0, "fallidos": []}
    if not sesiones:
        return {"estado": "error", "error": "No hay sesiones para publicar.", "publicados": 0, "fallidos": []}

    publicados = 0
    fallidos = []

    with sync_playwright() as playwright:
        contexto, pagina = _iniciar_sesion_blackboard(playwright, notificar)
        if pagina is None:
            return {
                "estado": "error",
                "error": "No hay una sesión activa. Inicia sesión primero.",
                "publicados": 0,
                "fallidos": [],
            }

        for sesion in sesiones:
            notificar(f"Creando sesión de Collaborate: {sesion['titulo']}...")
            try:
                if _crear_una_sesion(pagina, id_curso, sesion, notificar):
                    publicados += 1
                    notificar(f"[OK] Creada: {sesion['titulo']}")
                else:
                    fallidos.append(sesion["titulo"])
            except Exception as error:
                notificar(f"[ERROR] No se pudo crear '{sesion['titulo']}': {error}")
                fallidos.append(sesion["titulo"])

        contexto.close()

    estado = "ok" if not fallidos else ("parcial" if publicados else "error")
    return {"estado": estado, "publicados": publicados, "fallidos": fallidos}


def eliminar_sesiones_en_blackboard(id_curso: str, notificar=None) -> dict:
    """Elimina de Blackboard Collaborate TODAS las sesiones del curso que
    Blackboard mismo marque como "(aún no ha comenzado)" (ver el módulo).

    No recibe una lista de títulos: entra a la lista real de Collaborate y
    la relee después de cada eliminación, así que siempre elimina lo que
    de verdad existe ahí en ese momento, sin importar si el nombre coincide
    con lo que el panel hubiera calculado. Nunca toca la sala del curso, ni
    una sesión en curso, ni una ya finalizada.

    Devuelve {"estado": "ok"|"parcial"|"error", "eliminados": N,
    "fallidos": [...], "error": "..."}.
    """
    notificar = notificar or print

    if not id_curso:
        return {"estado": "error", "error": "No se pudo identificar el curso en Blackboard.", "eliminados": 0, "fallidos": []}

    eliminados = 0
    fallidos = []
    ya_intentados = set()

    with sync_playwright() as playwright:
        contexto, pagina = _iniciar_sesion_blackboard(playwright, notificar)
        if pagina is None:
            return {
                "estado": "error",
                "error": "No hay una sesión activa. Inicia sesión primero.",
                "eliminados": 0,
                "fallidos": [],
            }

        while True:
            frame_lista = _abrir_lista_de_sesiones(pagina, id_curso, notificar)
            if frame_lista is None:
                notificar("[ERROR] No se pudo abrir la lista de sesiones de Collaborate.")
                break

            pendientes = [t for t in _listar_titulos_no_iniciados(frame_lista) if t not in ya_intentados]
            if not pendientes:
                break

            titulo = pendientes[0]
            ya_intentados.add(titulo)
            notificar(f"Eliminando sesión de Collaborate: {titulo}...")
            try:
                if _eliminar_una_sesion(pagina, frame_lista, titulo, notificar):
                    eliminados += 1
                    notificar(f"[OK] Eliminada: {titulo}")
                else:
                    fallidos.append(titulo)
            except Exception as error:
                notificar(f"[ERROR] No se pudo eliminar '{titulo}': {error}")
                fallidos.append(titulo)

        contexto.close()

    estado = "ok" if not fallidos else ("parcial" if eliminados else "error")
    return {"estado": estado, "eliminados": eliminados, "fallidos": fallidos}
