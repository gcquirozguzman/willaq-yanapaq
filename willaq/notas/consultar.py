"""
Lectura de las notas de un curso desde el Libro de calificaciones de
Blackboard (solo lee: este módulo nunca escribe ni publica nada).

Cómo funciona (confirmado navegando de verdad con la sesión guardada; los
selectores de abajo salen del HTML real, no están inventados):

1. Se entra directo a
   https://cibertec.blackboard.com/ultra/courses/<id>/grades?gradebookView=list.
   Ese "?gradebookView=list" es exactamente lo que deja activo el botón
   "Ver lista de cursos" de la barra del libro de calificaciones, así que
   navegando con la URL ya se llega a la vista de lista sin tener que
   hacer clic en el botón. Igual se revisa el botón (aria-pressed) y, si
   por lo que sea la página quedó en la vista de cuadrícula, se hace clic.
2. La lista carga por tandas: al final hay un botón "Cargar N más
   elementos del libro de calificaciones" (button.load-more-items). Es un
   botón "sr-only" (existe para lectores de pantalla pero está fuera de la
   pantalla), así que un clic por coordenadas de Playwright falla siempre
   con "element is outside of the viewport"; se dispara un click() de DOM,
   igual que en willaq/dictado/publicar.py. Se repite hasta que el botón
   quede deshabilitado.
3. Cada elemento calificable es un enlace
   a[analytics-id="components.directives.grade.graderColumn.name.link"];
   su categoría ("Actividad", "Cuestionario", "Asistencia"...) está en la
   segunda celda de su fila (td[aria-colindex="2"]).
4. Al hacer clic en uno de esos enlaces, Blackboard navega a
   .../assessment/test/<id_elemento>?gradeitemView=students, que es la
   lista de alumnos con su nota. Ese id no se puede adivinar desde la
   lista (los enlaces son href="javascript:void(0);"), por eso siempre se
   llega haciendo clic y no armando la URL a mano.

Sobre leer la lista de alumnos, dos cosas que no son obvias y que se
descubrieron probando contra el curso real:

- La lista está VIRTUALIZADA: solo se renderizan de verdad las filas que
  caben en pantalla, y las demás quedan como <div
  class="intersection-observable-placeholder"> vacíos. Por eso el
  navegador se abre con una ventana deliberadamente alta (ver
  ALTO_VENTANA): así entran las 25 filas de una página y se pueden leer
  todas de una sola vez. Si aun así quedaran placeholders, se hace scroll
  hasta el final y se vuelve a intentar.
- La lista está PAGINADA de a 25 alumnos (78 alumnos = 4 páginas). Se
  avanza con el botón "Página siguiente"
  (button.js-pagination-page-up-button) hasta que queda deshabilitado. En
  vez de esperar un tiempo fijo tras cada clic, se espera a que de verdad
  cambie el primer alumno de la lista.

Qué se descarta al listar los elementos calificables:

- Todo elemento cuyo NOMBRE contenga "cuestionario" (eso cubre también
  "Minicuestionario", que contiene la misma palabra). El filtro es por
  nombre y no por categoría a propósito: "Examen Certificado" está en la
  categoría "Cuestionario" pero es un examen de verdad del curso, así que
  filtrar por categoría lo haría desaparecer de la lista.
- Las columnas que no son un examen ni una actividad, sino un total o un
  resumen: "Calificación general", "Total" y "Asistencia". Se comprobó
  contra el curso real que ninguna de las tres abre una lista de notas por
  alumno al hacerles clic (no hay nada que leer ahí), así que ofrecerlas
  sería ofrecer algo que siempre falla. Se reconocen por el ícono de su
  fila, que Blackboard etiqueta con el tipo de columna ("Cálculos",
  "Calificación general", "Asistencia", frente a "Actividad" o "Examen"
  de los elementos de verdad). Se descartan por ese tipo y no por su
  nombre para no depender de cómo se llame la columna en cada curso, y se
  usa una lista de tipos a descartar (y no una de tipos permitidos) para
  que un tipo calificable que aquí no se haya visto todavía siga
  apareciendo en vez de quedar oculto.
- Los nombres repetidos: Blackboard muestra "Calificación general" y
  "Total" dos veces en la vista de lista (una vez como columna fija y otra
  dentro del listado). Se deja solo la primera aparición de cada nombre.

Y al leer las notas se descarta el usuario "..._PreviewUser", que no es un
alumno: es la cuenta de "Vista previa del estudiante" del propio docente.
"""

from playwright.sync_api import sync_playwright

from willaq.autenticacion.login import URL_BLACKBOARD, _esperar_carga_de_pagina
from willaq.dictado.publicar import _iniciar_sesion_blackboard

# Ventana alta a propósito: la lista de alumnos virtualiza sus filas y solo
# renderiza las visibles (ver el encabezado del módulo). Con 3000px de alto
# entran las 25 filas de una página del libro de calificaciones.
ANCHO_VENTANA = 1600
ALTO_VENTANA = 3000

# Selectores confirmados con el HTML real del libro de calificaciones.
SELECTOR_ENLACE_ELEMENTO = 'a[analytics-id="components.directives.grade.graderColumn.name.link"]'
SELECTOR_TOGGLE_VISTA_LISTA = '[data-analytics-id="component.gradebook.view.toolbar.toggle-list"]'
SELECTOR_BOTON_CARGAR_MAS = "button.load-more-items"
SELECTOR_FILA_ALUMNO = ".submission-list-row[data-student-id]"
SELECTOR_BOTON_PAGINA_SIGUIENTE = "button.js-pagination-page-up-button"
SELECTOR_PLACEHOLDER_FILA = ".intersection-observable-placeholder"

# Tipos de columna (los que Blackboard pone como etiqueta del ícono de cada
# fila) que NO tienen notas por alumno: son totales o resúmenes del curso.
# Ver el encabezado del módulo.
TIPOS_SIN_NOTAS_POR_ALUMNO = {"cálculos", "calificación general", "asistencia"}

# Lee de un tirón, dentro del navegador, los elementos calificables de la
# vista de lista. Se hace en un solo evaluate() en vez de con un locator por
# campo: son ~17 elementos x 2 campos, y cada locator es un viaje de ida y
# vuelta al navegador.
JS_LEER_ELEMENTOS = """
(selectorEnlace) => {
  const limpiar = (el) => (el ? el.textContent.replace(/\\s+/g, ' ').trim() : null);
  return Array.from(document.querySelectorAll(selectorEnlace)).map((enlace) => {
    const fila = enlace.closest('tr');
    // El ícono de la fila lleva como etiqueta accesible el tipo de columna
    // ("Actividad", "Examen", "Cálculos", "Asistencia"...): es lo que
    // permite descartar los totales y resúmenes del curso.
    const icono = fila ? fila.querySelector('svg[aria-label]') : null;
    return {
      nombre: limpiar(enlace),
      categoria: fila ? limpiar(fila.querySelector('td[aria-colindex="2"]')) : null,
      tipo: icono ? icono.getAttribute('aria-label') : null,
    };
  });
}
"""

# Lo mismo para la lista de alumnos: 25 filas x 7 campos por página serían
# 175 viajes al navegador por página si se hiciera con locators.
JS_LEER_ALUMNOS = """
(selectorFila) => {
  const limpiar = (el) => (el ? el.textContent.replace(/\\s+/g, ' ').trim() : null);
  return Array.from(document.querySelectorAll(selectorFila)).map((fila) => {
    // El estado de calificación ("Completado", "Nada para calificar") vive
    // en el mismo bloque que su propio encabezado para móvil; se clona el
    // bloque y se le quita el encabezado para quedarse solo con el valor.
    let estadoNota = null;
    const bloqueEstado = fila.querySelector('.js-submission-date');
    if (bloqueEstado) {
      const copia = bloqueEstado.cloneNode(true);
      copia.querySelectorAll('.status-header').forEach((el) => el.remove());
      estadoNota = limpiar(copia) || null;
    }
    const campoNota = fila.querySelector('input.js-grade-input');
    // La nota está en un <input> (es editable para el docente), así que hay
    // que leer su .value: no aparece en el texto de la fila. Cuando el
    // elemento tiene rúbrica, el input queda oculto y el valor se muestra
    // en un .grade-point-value; por eso se prueban los dos.
    const notaInput = campoNota ? campoNota.value.trim() : '';
    return {
      id: fila.getAttribute('data-student-id'),
      alumno: limpiar(fila.querySelector('bb-ui-username bdi')),
      nota: notaInput || limpiar(fila.querySelector('.grade-point-value')) || null,
      sobre: limpiar(fila.querySelector('.points-text')),
      estado_entrega: limpiar(fila.querySelector('.js-student-status-value')),
      estado_nota: estadoNota,
      actividad: limpiar(fila.querySelector('.js-submission-activity-label')),
      publicado: limpiar(fila.querySelector('.js-grade-posted')) !== null,
      nota_automatica: limpiar(fila.querySelector('.override-indicator')),
    };
  });
}
"""


def es_cuestionario(nombre: str) -> bool:
    """True si el nombre del elemento lo marca como cuestionario.

    Cubre "Cuestionario" y "Minicuestionario" con la misma comprobación,
    porque el segundo contiene al primero como subcadena.
    """
    return "cuestionario" in (nombre or "").lower()


def _limpiar_sobre(texto):
    """Convierte el "/20" que muestra Blackboard en el número 20 (como texto)."""
    if not texto:
        return None
    solo_numero = texto.replace("/", "").strip()
    return solo_numero or None


def _abrir_libro_de_calificaciones(pagina, id_curso: str, notificar) -> bool:
    """Deja la página en la vista de lista del libro, con todo ya cargado."""
    pagina.goto(f"{URL_BLACKBOARD}ultra/courses/{id_curso}/grades?gradebookView=list")
    _esperar_carga_de_pagina(pagina)

    try:
        pagina.locator(SELECTOR_ENLACE_ELEMENTO).first.wait_for(timeout=40_000)
    except Exception as error:
        notificar(f"[ERROR] No cargó el libro de calificaciones del curso: {error}")
        return False

    # La URL ya pide la vista de lista, así que normalmente esto no hace
    # nada; queda como respaldo por si la página abriera en cuadrícula.
    toggle = pagina.locator(SELECTOR_TOGGLE_VISTA_LISTA)
    if toggle.count() > 0 and toggle.first.get_attribute("aria-pressed") != "true":
        try:
            toggle.first.evaluate("el => el.click()")
            pagina.locator(SELECTOR_ENLACE_ELEMENTO).first.wait_for(timeout=20_000)
        except Exception as error:
            notificar(f"[AVISO] No se pudo cambiar a la vista de lista: {error}")

    _cargar_todos_los_elementos(pagina, notificar)
    return True


def _cargar_todos_los_elementos(pagina, notificar):
    """Pulsa "Cargar más elementos" hasta que ya no quede nada por cargar."""
    for _ in range(30):
        boton = pagina.locator(SELECTOR_BOTON_CARGAR_MAS)
        if boton.count() == 0 or boton.first.is_disabled():
            return
        antes = pagina.locator(SELECTOR_ENLACE_ELEMENTO).count()
        try:
            # click() de DOM: el botón es "sr-only" y queda fuera de la
            # pantalla, así que un clic por coordenadas nunca lo alcanza.
            boton.first.evaluate("el => el.click()")
        except Exception as error:
            notificar(f"[AVISO] No se pudieron cargar más elementos: {error}")
            return
        # Se espera a que aparezcan elementos nuevos de verdad, en vez de a
        # un tiempo fijo; si no aparece ninguno, ya no hay más que cargar.
        for _ in range(24):
            pagina.wait_for_timeout(250)
            if pagina.locator(SELECTOR_ENLACE_ELEMENTO).count() > antes:
                break
        else:
            return


def _leer_elementos(pagina) -> list:
    """Lista los elementos calificables visibles, sin filtrar nada todavía."""
    return pagina.evaluate(JS_LEER_ELEMENTOS, SELECTOR_ENLACE_ELEMENTO)


def _filtrar_elementos(elementos: list) -> list:
    """Quita cuestionarios, totales/resúmenes y repetidos (ver el módulo)."""
    filtrados = []
    nombres_vistos = set()
    for elemento in elementos:
        nombre = elemento.get("nombre")
        if not nombre or es_cuestionario(nombre) or nombre in nombres_vistos:
            continue
        if (elemento.get("tipo") or "").strip().lower() in TIPOS_SIN_NOTAS_POR_ALUMNO:
            continue
        nombres_vistos.add(nombre)
        filtrados.append(elemento)
    return filtrados


def _esperar_filas_renderizadas(pagina):
    """Espera a que las filas de alumnos estén renderizadas de verdad.

    La lista virtualiza: las filas fuera de pantalla quedan como
    placeholders vacíos. Con la ventana alta que usa este módulo eso no
    debería pasar, pero si pasara se hace scroll hasta el final para
    forzar que se rendericen antes de leerlas.
    """
    for _ in range(4):
        if pagina.locator(SELECTOR_PLACEHOLDER_FILA).count() == 0:
            return
        pagina.mouse.wheel(0, 4000)
        pagina.wait_for_timeout(600)


def _leer_pagina_de_alumnos(pagina) -> list:
    _esperar_filas_renderizadas(pagina)
    return pagina.evaluate(JS_LEER_ALUMNOS, SELECTOR_FILA_ALUMNO)


def _id_primer_alumno(pagina):
    filas = pagina.locator(SELECTOR_FILA_ALUMNO)
    if filas.count() == 0:
        return None
    return filas.first.get_attribute("data-student-id")


def _leer_todas_las_paginas(pagina, notificar) -> list:
    """Recorre la lista paginada de alumnos y devuelve todas sus filas."""
    alumnos = []
    ids_vistos = set()

    for numero_pagina in range(1, 60):
        notificar(f"Leyendo página {numero_pagina} de la lista de alumnos...")
        for fila in _leer_pagina_de_alumnos(pagina):
            if fila.get("id") in ids_vistos:
                continue
            ids_vistos.add(fila.get("id"))
            alumnos.append(fila)

        siguiente = pagina.locator(SELECTOR_BOTON_PAGINA_SIGUIENTE)
        if siguiente.count() == 0 or siguiente.first.is_disabled():
            break

        id_antes = _id_primer_alumno(pagina)
        siguiente.first.click()
        # Se espera a que la lista cambie de verdad (otro primer alumno) en
        # vez de a un tiempo fijo, que sería más lento y menos confiable.
        for _ in range(60):
            pagina.wait_for_timeout(250)
            if _id_primer_alumno(pagina) != id_antes:
                break
        else:
            notificar("[AVISO] La lista de alumnos no avanzó a la página siguiente; se corta ahí.")
            break

    return alumnos


def obtener_elementos_calificables(id_curso: str, notificar=None) -> dict:
    """Lista los elementos calificables del curso (exámenes, actividades...).

    Devuelve {"estado": "ok"|"error", "elementos": [{"nombre", "categoria"}],
    "error": "..."}. Los cuestionarios y los nombres repetidos ya vienen
    descartados (ver el encabezado del módulo).
    """
    notificar = notificar or print

    if not id_curso:
        return {"estado": "error", "error": "No se pudo identificar el curso en Blackboard.", "elementos": []}

    with sync_playwright() as playwright:
        contexto, pagina = _iniciar_sesion_blackboard(playwright, notificar)
        if pagina is None:
            return {
                "estado": "error",
                "error": "No hay una sesión activa. Inicia sesión primero.",
                "elementos": [],
            }

        try:
            pagina.set_viewport_size({"width": ANCHO_VENTANA, "height": ALTO_VENTANA})
            notificar("Abriendo el libro de calificaciones del curso...")
            if not _abrir_libro_de_calificaciones(pagina, id_curso, notificar):
                return {
                    "estado": "error",
                    "error": "No se pudo abrir el libro de calificaciones del curso.",
                    "elementos": [],
                }

            elementos = _filtrar_elementos(_leer_elementos(pagina))
            notificar(f"Se encontraron {len(elementos)} elemento(s) calificable(s) (sin contar cuestionarios).")
            return {"estado": "ok", "elementos": elementos}
        finally:
            contexto.close()


def obtener_notas_de_elemento(id_curso: str, nombre_elemento: str, notificar=None) -> dict:
    """Devuelve la nota de todos los alumnos para un elemento del curso.

    Devuelve {"estado": "ok"|"error", "elemento": "...", "sobre": "20",
    "alumnos": [{"alumno", "nota", "sobre", "estado_entrega", ...}],
    "error": "..."}.
    """
    notificar = notificar or print

    if not id_curso:
        return {"estado": "error", "error": "No se pudo identificar el curso en Blackboard.", "alumnos": []}
    if not nombre_elemento:
        return {"estado": "error", "error": "No se indicó de qué elemento leer las notas.", "alumnos": []}

    with sync_playwright() as playwright:
        contexto, pagina = _iniciar_sesion_blackboard(playwright, notificar)
        if pagina is None:
            return {
                "estado": "error",
                "error": "No hay una sesión activa. Inicia sesión primero.",
                "alumnos": [],
            }

        try:
            pagina.set_viewport_size({"width": ANCHO_VENTANA, "height": ALTO_VENTANA})
            notificar("Abriendo el libro de calificaciones del curso...")
            if not _abrir_libro_de_calificaciones(pagina, id_curso, notificar):
                return {
                    "estado": "error",
                    "error": "No se pudo abrir el libro de calificaciones del curso.",
                    "alumnos": [],
                }

            # Se busca el enlace por su nombre exacto dentro del navegador y
            # se hace clic por posición: los enlaces son
            # href="javascript:void(0);", así que no hay ninguna URL que se
            # pueda armar a mano para llegar a la lista de alumnos.
            indice = pagina.evaluate(
                """({ selector, nombre }) => {
                    const enlaces = Array.from(document.querySelectorAll(selector));
                    return enlaces.findIndex(
                      (a) => a.textContent.replace(/\\s+/g, ' ').trim() === nombre
                    );
                }""",
                {"selector": SELECTOR_ENLACE_ELEMENTO, "nombre": nombre_elemento},
            )
            if indice is None or indice < 0:
                return {
                    "estado": "error",
                    "error": f"No se encontró '{nombre_elemento}' en el libro de calificaciones del curso.",
                    "alumnos": [],
                }

            notificar(f"Abriendo las notas de '{nombre_elemento}'...")
            pagina.locator(SELECTOR_ENLACE_ELEMENTO).nth(indice).click()

            try:
                pagina.locator(SELECTOR_FILA_ALUMNO).first.wait_for(timeout=45_000)
            except Exception:
                return {
                    "estado": "error",
                    "error": (
                        f"'{nombre_elemento}' no abre una lista de notas por alumno en Blackboard. "
                        "Elige un examen o una actividad."
                    ),
                    "alumnos": [],
                }

            filas = _leer_todas_las_paginas(pagina, notificar)
        finally:
            contexto.close()

    # El "..._PreviewUser" es la cuenta de "Vista previa del estudiante" del
    # propio docente, no un alumno del curso.
    alumnos = [fila for fila in filas if not (fila.get("alumno") or "").endswith("_PreviewUser")]
    for alumno in alumnos:
        alumno["sobre"] = _limpiar_sobre(alumno.get("sobre"))

    sobre = next((alumno["sobre"] for alumno in alumnos if alumno.get("sobre")), None)
    notificar(f"Se leyeron las notas de {len(alumnos)} alumno(s).")

    return {"estado": "ok", "elemento": nombre_elemento, "sobre": sobre, "alumnos": alumnos}
