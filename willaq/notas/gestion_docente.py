"""
Lee del portal de Gestión Docente los tipos de nota que se pueden registrar
en un curso (T1, T2, EF, RE...).

Este camino es bastante más largo que el de Blackboard, y no se puede
acortar: el portal solo habilita esa lista al final de todo el recorrido.

    1. Entrar al portal con el usuario y la contraseña guardados.
    2. Hacer clic en el aplicativo "Académico" (abre una pestaña nueva).
    3. Ir a la pantalla de Registro de Notas.
    4. Buscar en la tabla la fila del curso elegido y pulsar su
       "Ingresar notas".
    5. Ahí el portal pide un TOKEN. Ese paso lo hace el docente a mano, en
       la ventana que queda abierta: escribe el token, pulsa "Validar
       token" y acepta el modal de confirmación. La herramienta no lo
       automatiza (ni podría: el token es justamente la comprobación de que
       hay una persona).
    6. Recién entonces el portal llena y habilita el combo de tipos de
       nota, y de ahí se leen.

Por eso el paso 5 no se espera con un tiempo fijo, sino mirando el propio
combo: mientras siga vacío o deshabilitado, el docente todavía no terminó.
"""

import time

from playwright.sync_api import sync_playwright

from willaq.autenticacion import credenciales
from willaq.autenticacion.gestion_docente import (
    SEGUNDOS_ENTRE_PASOS,
    _abrir_aplicativo_academico,
    _abrir_registro_de_notas_en_pagina,
    _entrar_al_portal,
)

# El combo de tipos de nota, confirmado con el HTML real de la pantalla.
SELECTOR_COMBO_TIPOS = "#cphSite_ddlNotas"

# La opción "SELECCIONE" viene siempre, con valor 0, y no es un tipo de
# nota: es el texto que muestra el combo mientras no eliges nada.
VALOR_OPCION_VACIA = "0"

# Cuánto se le da al docente para escribir el token, validarlo y aceptar el
# modal. Es generoso a propósito: el token lo tiene que ir a buscar a otro
# lado, y quedarse corto significaría perder todo el recorrido anterior.
SEGUNDOS_MAXIMOS_TOKEN = 900
SEGUNDOS_ENTRE_SONDEOS_TOKEN = 1.0

# Busca en la tabla de Registro de Notas la fila del curso y le marca su
# botón "Ingresar notas", para que después Playwright pueda pulsarlo por esa
# marca. Se resuelve dentro de la página, de una sola vez, porque hace falta
# mirar el texto de cada fila y de cada botón: hacerlo con consultas sueltas
# desde Python sería mucho más lento y mucho más frágil.
JS_MARCAR_BOTON_INGRESAR = """
([codigos, seccion]) => {
  const limpiar = (t) => (t || "")
    .normalize("NFKD")
    .replace(/[\\u0300-\\u036f]/g, "")
    .toLowerCase();
  const resumen = (f) => (f.innerText || "").replace(/\\s+/g, " ").trim().slice(0, 140);

  const filas = Array.from(document.querySelectorAll("tr"));
  // Los códigos vienen en orden de preferencia y se prueban de uno en uno:
  // el primero es el de la asignatura, que es el que de verdad identifica
  // al curso. Los siguientes son tramos sueltos del código de Blackboard
  // (por ejemplo el período), que sirven de red por si el primero falla
  // pero que por sí solos coincidirían con casi cualquier fila.
  let candidatas = [];
  for (const codigo of codigos) {
    if (!codigo) continue;
    candidatas = filas.filter((fila) => limpiar(fila.innerText).includes(limpiar(codigo)));
    if (candidatas.length) break;
  }
  if (candidatas.length === 0) {
    return { encontrado: false, motivo: "sin_fila", filas: filas.length };
  }

  // Si el mismo curso aparece en varias secciones, se queda con la fila
  // cuya sección coincide exactamente con la del curso elegido.
  let fila = candidatas[0];
  if (seccion && candidatas.length > 1) {
    const conSeccion = candidatas.find((f) =>
      Array.from(f.cells || []).some((celda) => celda.innerText.trim() === seccion)
    );
    if (conSeccion) fila = conSeccion;
  }

  const controles = Array.from(
    fila.querySelectorAll('a, button, input[type="submit"], input[type="button"], img')
  );
  const esIngresar = (c) =>
    limpiar(c.innerText || c.value || c.title || c.alt || "").includes("ingresar");

  let objetivo = controles.find(esIngresar);
  // Si ningún control lo dice con todas sus letras pero la fila tiene uno
  // solo, ese es: la tabla trae un botón por curso.
  if (!objetivo && controles.length === 1) objetivo = controles[0];
  if (!objetivo) {
    return { encontrado: false, motivo: "sin_boton", fila: resumen(fila) };
  }

  // Si lo que se encontró es la imagen dentro del botón, se pulsa el
  // enlace o botón que la contiene, no la imagen suelta.
  const pulsable = objetivo.closest('a, button, input') || objetivo;
  pulsable.setAttribute("data-willaq-objetivo", "1");
  return {
    encontrado: true,
    fila: resumen(fila),
    texto: (pulsable.innerText || pulsable.value || pulsable.title || "").trim(),
  };
}
"""

JS_LEER_TIPOS = """
(selector) => {
  const combo = document.querySelector(selector);
  if (!combo || combo.disabled) return null;
  return Array.from(combo.options).map((opcion) => ({
    valor: opcion.value,
    texto: (opcion.text || "").trim(),
  }));
}
"""


def _codigos_a_buscar(curso: dict) -> list:
    """Con qué textos se intenta reconocer al curso dentro de la tabla.

    En Blackboard el curso viene como "CIBERTEC.ALED5471.202607P.30" y
    "ALED5471 INTRODUCCION A LA ALGORITMIA". Gestión Docente no usa ese
    código largo, sino el de la asignatura ("ALED5471"), así que se prueban
    los dos: primero la primera palabra del nombre, que es el que suele
    coincidir, y después los tramos del código por si acaso.
    """
    candidatos = []

    nombre = (curso.get("nombre") or "").strip()
    if nombre:
        candidatos.append(nombre.split()[0])

    for tramo in (curso.get("codigo") or "").split("."):
        tramo = tramo.strip()
        # "CIBERTEC" aparece en todos los cursos, así que no distingue nada,
        # y los tramos muy cortos harían coincidir cualquier fila.
        if len(tramo) >= 4 and tramo.upper() != "CIBERTEC":
            candidatos.append(tramo)

    # Sin repetidos, conservando el orden de preferencia.
    vistos = set()
    return [c for c in candidatos if not (c.upper() in vistos or vistos.add(c.upper()))]


def _seccion_del_curso(curso: dict) -> str:
    """La sección del curso: el último tramo del código de Blackboard."""
    tramos = [t.strip() for t in (curso.get("codigo") or "").split(".") if t.strip()]
    return tramos[-1] if tramos else ""


def _marco_con_combo(pagina):
    """Devuelve el marco donde está el combo de tipos de nota, o None.

    Se miran también los iframes porque estas pantallas de intranet suelen
    abrir su contenido dentro de uno.
    """
    try:
        for marco in pagina.frames:
            try:
                if marco.query_selector(SELECTOR_COMBO_TIPOS) is not None:
                    return marco
            except Exception:
                continue
    except Exception:
        pass
    return None


def _leer_tipos_del_combo(marco) -> list:
    """Lee las opciones del combo, sin la opción vacía. [] si aún no sirve."""
    try:
        opciones = marco.evaluate(JS_LEER_TIPOS, SELECTOR_COMBO_TIPOS)
    except Exception:
        return []
    if not opciones:
        return []
    return [
        {"valor": o["valor"], "nombre": o["texto"]}
        for o in opciones
        if o.get("valor") and o["valor"] != VALOR_OPCION_VACIA and o.get("texto")
    ]


def _esperar_a_que_el_docente_valide_el_token(pagina, notificar, cancelado) -> list:
    """Espera a que el token se valide y el combo de tipos quede lleno.

    No hay forma de saber "ya validó" mirando otra cosa: el propio combo es
    la señal. Mientras siga sin existir, deshabilitado o con la única opción
    de "SELECCIONE", se sigue esperando.
    """
    intentos = int(SEGUNDOS_MAXIMOS_TOKEN / SEGUNDOS_ENTRE_SONDEOS_TOKEN)
    aviso_repetido = int(60 / SEGUNDOS_ENTRE_SONDEOS_TOKEN)

    for numero in range(intentos):
        if cancelado is not None and cancelado():
            notificar("Se canceló la espera del token desde el panel.")
            return []
        if pagina.is_closed():
            notificar("[AVISO] Se cerró la ventana antes de validar el token.")
            return []

        marco = _marco_con_combo(pagina)
        if marco is not None:
            tipos = _leer_tipos_del_combo(marco)
            if tipos:
                return tipos

        if numero and numero % aviso_repetido == 0:
            notificar(f"Sigo esperando el token... ({numero // aviso_repetido} min)")
        time.sleep(SEGUNDOS_ENTRE_SONDEOS_TOKEN)

    notificar("[AVISO] Se acabó el tiempo de espera del token.")
    return []


def obtener_tipos_nota(curso: dict, notificar=None, cancelado=None, marcar_esperando_token=None) -> dict:
    """Recorre el portal hasta la pantalla de notas del curso y lee sus tipos.

    'curso' es el curso tal como lo guarda el panel ({"codigo", "nombre",
    ...}). La ventana se abre a la vista siempre, sin excepción: el docente
    tiene que escribir el token ahí.

    Devuelve {"estado": "ok"|"sin_credenciales"|"credenciales"|"error",
    "tipos": [{"valor", "nombre"}], "error": "..."}.
    """
    notificar = notificar or print
    marcar_esperando_token = marcar_esperando_token or (lambda: None)

    guardadas = credenciales.cargar()
    if guardadas is None:
        notificar("[AVISO] Falta guardar tu usuario y contraseña de Gestión Docente.")
        notificar('        Hazlo con "Iniciar sesión" en la tarjeta de sesiones.')
        return {"estado": "sin_credenciales", "tipos": []}

    codigos = _codigos_a_buscar(curso)
    seccion = _seccion_del_curso(curso)
    if not codigos:
        return {"estado": "error", "tipos": [], "error": "No se pudo saber el código del curso."}

    with sync_playwright() as playwright:
        navegador = playwright.chromium.launch(headless=False)
        contexto = navegador.new_context(no_viewport=True)
        try:
            pagina = contexto.new_page()

            notificar("Abriendo Gestión Docente...")
            resultado = _entrar_al_portal(
                pagina, guardadas["usuario"], guardadas["clave"], notificar
            )
            if resultado == "credenciales":
                credenciales.olvidar()
                notificar("[AVISO] El portal rechazó el usuario o la contraseña guardados.")
                return {"estado": "credenciales", "tipos": []}
            if resultado != "ok":
                return {"estado": "error", "tipos": [], "error": "No se pudo entrar a Gestión Docente."}

            pagina = _abrir_aplicativo_academico(pagina, notificar) or pagina

            notificar("Abriendo Registro de Notas...")
            if not _abrir_registro_de_notas_en_pagina(pagina, notificar):
                return {
                    "estado": "error",
                    "tipos": [],
                    "error": "El portal no dejó abrir Registro de Notas.",
                }

            notificar(f"Buscando el curso {codigos[0]} en la tabla...")
            time.sleep(SEGUNDOS_ENTRE_PASOS)
            marcado = pagina.evaluate(JS_MARCAR_BOTON_INGRESAR, [codigos, seccion])
            if not marcado.get("encontrado"):
                if marcado.get("motivo") == "sin_fila":
                    error = f"No se encontró el curso {codigos[0]} en Registro de Notas."
                else:
                    error = f'No se encontró el botón "Ingresar notas" del curso {codigos[0]}.'
                notificar(f"[AVISO] {error}")
                return {"estado": "error", "tipos": [], "error": error}

            notificar(f"Curso encontrado: {marcado.get('fila')}")
            notificar('Pulsando "Ingresar notas"...')
            pagina.click('[data-willaq-objetivo="1"]')
            time.sleep(SEGUNDOS_ENTRE_PASOS)

            notificar("=" * 60)
            notificar("AHORA TE TOCA A TI, en la ventana del navegador:")
            notificar("  1. Escribe el token.")
            notificar('  2. Pulsa "Validar token".')
            notificar("  3. Acepta el modal de confirmación que aparece.")
            notificar("Cuando el portal habilite la lista de notas, sigo yo solo.")
            notificar("=" * 60)
            marcar_esperando_token()

            tipos = _esperar_a_que_el_docente_valide_el_token(pagina, notificar, cancelado)
            if not tipos:
                return {
                    "estado": "error",
                    "tipos": [],
                    "error": "No se llegó a habilitar la lista de tipos de nota.",
                }

            notificar(f"[OK] Se encontraron {len(tipos)} tipo(s) de nota:")
            for tipo in tipos:
                notificar(f"     - {tipo['nombre']}")
            return {"estado": "ok", "tipos": tipos}
        except Exception as error:
            notificar(f"[ERROR] Ocurrió un problema en Gestión Docente: {error}")
            return {"estado": "error", "tipos": [], "error": str(error)}
        finally:
            try:
                navegador.close()
            except Exception:
                pass
