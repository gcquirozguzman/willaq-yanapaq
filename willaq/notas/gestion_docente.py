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
from willaq.notas.calculo import normalizar_nombre
from willaq.autenticacion.gestion_docente import (
    SEGUNDOS_ENTRE_PASOS,
    _abrir_aplicativo_academico,
    _abrir_registro_de_notas_en_pagina,
    _entrar_al_portal,
    _esperar_carga_de_pagina,
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

# Cuánto se espera después de cada acción que dispara un postback de
# ASP.NET (elegir el tipo de nota, quitar el check). La página se recarga
# entera, así que leerla antes de tiempo da la versión vieja.
SEGUNDOS_TRAS_POSTBACK = 6
SEGUNDOS_MAXIMOS_REFRESCO = 45

# El check "Mostrar sólo alumnos HABILITADOS" viene marcado cada vez que se
# elige un tipo de nota, y mientras siga así la lista está recortada: solo
# muestra a los habilitados. Por eso hay que quitarlo SIEMPRE después de
# elegir en el combo, no una sola vez.
#
# Dos detalles del HTML real que importan: es un checkbox de Bootstrap
# (clase "custom-control-input"), así que el <input> está oculto y lo que se
# ve es su <label>; y su onclick dispara un __doPostBack, o sea que la
# página se recarga entera y hay que esperarla.
SELECTOR_CHECK_SOLO_HABILITADOS = "#cphSite_chkSoloHab"

# La tabla de alumnos de la pantalla de notas, confirmada con su HTML real.
SELECTOR_TABLA_ALUMNOS = "#cphSite_gvNotas"

# Cuántas lecturas seguidas iguales hacen falta para dar por terminado el
# refresco de la tabla. Con una sola no alcanza: el postback puede estar a
# medio camino y la tabla verse quieta por un instante.
LECTURAS_IGUALES_PARA_DAR_POR_LISTO = 3

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

# Mira cómo está el check de "sólo habilitados". Se busca primero por su id
# conocido y, si el portal lo cambiara, se cae al primer checkbox marcado
# que haya. Devuelve además la lista de checks de la pantalla, que queda en
# el registro técnico por si alguna vez hay que ajustar el selector.
JS_ESTADO_DEL_CHECK = """
(selector) => {
  const etiquetaDe = (c) => {
    if (c.id) {
      const etiqueta = document.querySelector('label[for="' + c.id + '"]');
      if (etiqueta) return etiqueta.innerText.trim();
    }
    const contenedor = c.closest("label, td, th, div");
    return contenedor ? (contenedor.innerText || "").trim().slice(0, 80) : "";
  };

  const checks = Array.from(document.querySelectorAll('input[type="checkbox"]'));
  const objetivo = document.querySelector(selector) || checks.find((c) => c.checked) || null;

  return {
    existe: !!objetivo,
    marcado: objetivo ? objetivo.checked : false,
    id: objetivo ? objetivo.id : "",
    etiqueta: objetivo ? etiquetaDe(objetivo) : "",
    todos: checks.map((c) => ({ id: c.id || "", marcado: c.checked, etiqueta: etiquetaDe(c) })).slice(0, 12),
  };
}
"""

# Destilda el check. Se hace con el .click() del propio elemento en vez de
# un clic del ratón a propósito: el input está oculto por Bootstrap (lo
# visible es su label), así que un clic por coordenadas no llega. Llamar a
# .click() sí dispara su onclick, que es el que hace el __doPostBack.
JS_QUITAR_CHECK = """
(selector) => {
  const objetivo = document.querySelector(selector);
  if (!objetivo || !objetivo.checked) return false;
  objetivo.click();
  return true;
}
"""

# Lee la lista de alumnos de la pantalla de notas (confirmado con el HTML
# real de #cphSite_gvNotas).
#
# El nombre NO está en una sola columna: la tabla trae "Ap. paterno",
# "Ap. materno" y "Nombres" por separado, así que se guardan las tres y el
# nombre completo se arma como Nombres + Ap. materno + Ap. paterno. Ojo con
# un detalle real de estos datos: en la mayoría de las filas "Ap. paterno"
# viene vacío (&nbsp;) y "Ap. materno" trae los dos apellidos juntos, así
# que las partes vacías simplemente se saltan.
#
# La versión anterior elegía "la celda con más letras" de cada fila y se
# traía la carrera ("INGENIERÍA DE SISTEMAS INFORMÁ"), que es más larga que
# el nombre. Ahora las columnas se ubican por su encabezado.
JS_LEER_ALUMNOS = """
(idTabla) => {
  // innerText deja los &nbsp; como \\u00a0; si no se limpian, una celda
  // "vacía" parecería tener contenido.
  const texto = (c) => (c ? (c.innerText || "").replace(/\\u00a0/g, " ").trim() : "");
  const limpiar = (t) => (t || "")
    .normalize("NFKD")
    .replace(/[\\u0300-\\u036f]/g, "")
    .toLowerCase();
  const letras = (t) => (t.match(/[A-Za-z]/g) || []).length;

  const encabezadosDe = (tabla) => {
    const primera = tabla.querySelector("tr");
    return primera ? Array.from(primera.cells || []).map(texto) : [];
  };
  const buscarColumna = (encabezados, patron) => encabezados.findIndex((t) => patron.test(limpiar(t)));

  const tablas = Array.from(document.querySelectorAll("table"));
  if (!tablas.length) return { filas: [], tablas: 0, motivo: "sin_tablas" };

  // Primero la tabla conocida; si el portal le cambiara el id, la que tenga
  // encabezados de alumno; y como último recurso, la que más filas tenga.
  let tabla =
    document.querySelector(idTabla) ||
    tablas.find(
      (t) => t.querySelectorAll("tr").length > 2 &&
             encabezadosDe(t).some((h) => /apellido|nombre|alumno/.test(limpiar(h)))
    ) ||
    tablas.reduce((a, b) => (b.querySelectorAll("tr").length > a.querySelectorAll("tr").length ? b : a));
  if (!tabla || tabla.querySelectorAll("tr").length < 2) {
    return { filas: [], tablas: tablas.length, motivo: "tabla_vacia" };
  }

  const encabezados = encabezadosDe(tabla);
  const cuerpo = Array.from(tabla.querySelectorAll("tr")).filter(
    (f) => (f.cells || []).length && f.querySelectorAll("td").length
  );
  if (!cuerpo.length) return { filas: [], tablas: tablas.length, motivo: "sin_filas" };

  const iPaterno = buscarColumna(encabezados, /ap.*paterno/);
  const iMaterno = buscarColumna(encabezados, /ap.*materno/);
  const iNombres = buscarColumna(encabezados, /^nombres?$|nombres/);
  const iCodigo = buscarColumna(encabezados, /codigo/);
  const iCarrera = buscarColumna(encabezados, /carrera/);
  const iNota = buscarColumna(encabezados, /nota/);

  const valorEn = (fila, i) => (i >= 0 ? texto(fila.cells[i]) : "");

  // Si no hay columnas de apellidos, se cae a la columna de texto con más
  // valores distintos: los nombres casi no se repiten, la carrera sí.
  let columnaSuelta = -1;
  if (iNombres < 0 && iPaterno < 0 && iMaterno < 0) {
    let mejor = -1;
    const columnas = Math.max(...cuerpo.map((f) => f.cells.length));
    for (let i = 0; i < columnas; i++) {
      const valores = cuerpo.map((f) => valorEn(f, i)).filter((v) => letras(v) >= 5 && v.includes(" "));
      if (valores.length < cuerpo.length * 0.8) continue;
      const distintos = new Set(valores).size / valores.length;
      if (distintos > mejor) {
        mejor = distintos;
        columnaSuelta = i;
      }
    }
    if (columnaSuelta < 0) return { filas: [], tablas: tablas.length, motivo: "sin_columna" };
  }

  const filas = [];
  for (const fila of cuerpo) {
    const nombres = valorEn(fila, iNombres);
    const materno = valorEn(fila, iMaterno);
    const paterno = valorEn(fila, iPaterno);

    const nombre =
      columnaSuelta >= 0
        ? valorEn(fila, columnaSuelta)
        : [nombres, materno, paterno].filter((p) => p).join(" ");
    if (letras(nombre) < 5) continue;

    // La nota vive dentro de un <input>, así que innerText no la ve.
    const campoNota = iNota >= 0 && fila.cells[iNota] ? fila.cells[iNota].querySelector("input") : null;

    filas.push({
      nombre: nombre,
      nombres: nombres,
      ap_materno: materno,
      ap_paterno: paterno,
      codigo: valorEn(fila, iCodigo),
      carrera: valorEn(fila, iCarrera),
      nota_actual: campoNota ? campoNota.value : valorEn(fila, iNota),
      id_campo_nota: campoNota ? campoNota.id : "",
    });
  }

  return {
    filas: filas,
    tablas: tablas.length,
    id_tabla: tabla.id || "",
    encabezados: encabezados,
    columnas: { nombres: iNombres, materno: iMaterno, paterno: iPaterno, codigo: iCodigo, nota: iNota },
  };
}
"""

# Cuenta las filas de la tabla de alumnos y se queda con una "firma" de su
# contenido. Sirve para saber si el portal ya refrescó la lista después de
# quitar el check: si aparecen los alumnos no habilitados, esto cambia.
JS_FIRMA_DE_LA_TABLA = """
(idTabla) => {
  const tabla = document.querySelector(idTabla);
  if (!tabla) return "";
  const filas = tabla.querySelectorAll("tbody tr");
  const ultima = filas.length ? (filas[filas.length - 1].innerText || "").trim().slice(0, 60) : "";
  return filas.length + "|" + ultima;
}
"""

# Escribe las notas en los campos de la tabla. No pulsa ningún botón de
# guardar: solo deja los valores puestos para que el docente los revise y
# decida él. Se disparan los eventos 'input' y 'change' a mano porque
# asignar .value por código no los dispara solo, y esta pantalla los usa
# para sus validadores (el (*) rojo que aparece si la nota no es válida).
JS_ESCRIBIR_NOTAS = """
(pares) => {
  let puestas = 0;
  const fallidas = [];
  for (const par of pares) {
    const campo = document.getElementById(par.id);
    if (!campo) {
      fallidas.push(par.id);
      continue;
    }
    campo.value = par.valor;
    campo.dispatchEvent(new Event("input", { bubbles: true }));
    campo.dispatchEvent(new Event("change", { bubbles: true }));
    puestas++;
  }
  return { puestas: puestas, fallidas: fallidas };
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


def elegir_tipo_y_preparar_lista(pagina, tipo, notificar) -> bool:
    """Elige un tipo de nota en el combo y deja la lista de alumnos completa.

    Son dos pasos que van siempre juntos: elegir en el combo dispara un
    postback que carga la lista, y esa lista llega recortada porque el
    portal vuelve a marcar "Mostrar sólo alumnos HABILITADOS" cada vez. Por
    eso el check se quita después de CADA elección, no una sola vez.
    """
    marco = _marco_con_combo(pagina)
    if marco is None:
        notificar("[AVISO] No se encontró el combo de tipos de nota.")
        return False

    try:
        notificar(f"Eligiendo \"{tipo['nombre']}\" para que cargue la lista de alumnos...")
        marco.select_option(SELECTOR_COMBO_TIPOS, tipo["valor"])
    except Exception as error:
        notificar(f"[AVISO] No se pudo elegir un tipo de nota: {error}")
        return False

    _esperar_carga_de_pagina(pagina)
    time.sleep(SEGUNDOS_TRAS_POSTBACK)

    return _quitar_check_de_solo_habilitados(pagina, notificar)


def _estado_del_check(pagina) -> dict:
    """Cómo está ahora el check de "sólo habilitados"."""
    marco = _marco_con_combo(pagina) or pagina
    try:
        return marco.evaluate(JS_ESTADO_DEL_CHECK, SELECTOR_CHECK_SOLO_HABILITADOS)
    except Exception:
        return {"existe": False, "marcado": False, "todos": []}


def _quitar_check_de_solo_habilitados(pagina, notificar) -> bool:
    """Destilda "Mostrar sólo alumnos HABILITADOS" y espera el refresco.

    Hay que hacerlo cada vez que se elige un tipo de nota: el portal vuelve
    a marcarlo, y mientras siga marcado la lista muestra solo a los alumnos
    habilitados, o sea que faltarían alumnos.
    """
    estado = _estado_del_check(pagina)

    for check in estado.get("todos", []):
        notificar(f"     check: id={check['id'] or '-'} marcado={check['marcado']} · {check['etiqueta']}")

    if not estado.get("existe"):
        notificar("[AVISO] No se encontró el check de alumnos habilitados.")
        return False
    if not estado.get("marcado"):
        notificar("     El check ya estaba quitado.")
        return True

    antes = _firma_de_la_tabla(pagina)
    notificar(f"Quitando el check \"{estado.get('etiqueta')}\" (lista actual: {antes})...")

    marco = _marco_con_combo(pagina) or pagina
    try:
        marco.evaluate(JS_QUITAR_CHECK, SELECTOR_CHECK_SOLO_HABILITADOS)
    except Exception as error:
        notificar(f"[AVISO] No se pudo quitar el check: {error}")
        return False

    _esperar_carga_de_pagina(pagina)
    return _esperar_a_que_refresque_la_lista(pagina, antes, notificar)


def _firma_de_la_tabla(pagina) -> str:
    """Cuántas filas tiene la lista ahora mismo y cómo termina."""
    marco = _marco_con_combo(pagina) or pagina
    try:
        return marco.evaluate(JS_FIRMA_DE_LA_TABLA, SELECTOR_TABLA_ALUMNOS) or ""
    except Exception:
        return ""


def _esperar_a_que_refresque_la_lista(pagina, antes: str, notificar) -> bool:
    """Espera a que la tabla de alumnos termine de recargarse.

    Es el paso que faltaba. No sirve mirar el propio check: al hacer
    .click() el navegador lo destilda en el acto, así que se ve "listo"
    cuando el servidor todavía no contestó, y la lista que se leía era la
    vieja (la recortada, sin los alumnos no habilitados).

    Lo que sí sirve es mirar la tabla: se espera a que CAMBIE respecto a
    como estaba y luego a que se quede quieta varias lecturas seguidas. Si
    nunca cambia se sigue igual: puede ser que todos los alumnos ya
    estuvieran habilitados y la lista sea de verdad la misma.
    """
    limite = time.time() + SEGUNDOS_MAXIMOS_REFRESCO
    cambio = False
    ultima = None
    iguales = 0

    while time.time() < limite:
        time.sleep(SEGUNDOS_ENTRE_SONDEOS_TOKEN)
        ahora = _firma_de_la_tabla(pagina)

        if ahora and ahora != antes:
            cambio = True
        if cambio:
            iguales = iguales + 1 if ahora == ultima else 0
            if iguales >= LECTURAS_IGUALES_PARA_DAR_POR_LISTO:
                notificar(f"[OK] La lista se refrescó: {antes} -> {ahora}")
                return True
        ultima = ahora

    if cambio:
        notificar(f"[AVISO] La lista siguió cambiando; se toma como está: {ultima}")
        return True

    notificar(f"[AVISO] La lista no cambió tras quitar el check (sigue en {antes}).")
    notificar("        Puede que todos los alumnos ya estuvieran habilitados.")
    return True


def _leer_alumnos(pagina, notificar) -> list:
    """Lee los nombres de los alumnos que quedaron listados en la pantalla."""
    marco = _marco_con_combo(pagina) or pagina
    try:
        leido = marco.evaluate(JS_LEER_ALUMNOS, SELECTOR_TABLA_ALUMNOS)
    except Exception as error:
        notificar(f"[AVISO] No se pudo leer la lista de alumnos: {error}")
        return []

    filas = leido.get("filas") or []
    if not filas:
        notificar(f"[AVISO] No se encontró la lista de alumnos ({leido.get('motivo')}).")
        return []

    notificar(f"[OK] Se leyeron {len(filas)} alumno(s) de la tabla {leido.get('id_tabla') or 'sin id'}.")
    notificar(f"     columnas: {', '.join(leido.get('encabezados') or [])}")
    for fila in filas[:3]:
        notificar(f"     ejemplo: {fila['codigo']} · {fila['nombre']}")
    return filas


def _llegar_hasta_los_tipos(pagina, curso, notificar, cancelado, marcar_esperando_token) -> dict:
    """Recorre el portal hasta tener el combo de tipos de nota habilitado.

    Es el camino que comparten las dos herramientas (leer los datos del
    curso y escribir las notas): portal → Académico → Registro de Notas →
    "Ingresar notas" del curso → token puesto por el docente.

    Devuelve {"estado": "ok"|"credenciales"|"error", "tipos": [...],
    "error": "..."}.
    """
    guardadas = credenciales.cargar()
    if guardadas is None:
        notificar("[AVISO] Falta guardar tu usuario y contraseña de Gestión Docente.")
        notificar('        Hazlo con "Iniciar sesión" en la tarjeta de sesiones.')
        return {"estado": "sin_credenciales", "tipos": []}

    codigos = _codigos_a_buscar(curso)
    seccion = _seccion_del_curso(curso)
    if not codigos:
        return {"estado": "error", "tipos": [], "error": "No se pudo saber el código del curso."}

    notificar("Abriendo Gestión Docente...")
    resultado = _entrar_al_portal(pagina, guardadas["usuario"], guardadas["clave"], notificar)
    if resultado == "credenciales":
        credenciales.olvidar()
        notificar("[AVISO] El portal rechazó el usuario o la contraseña guardados.")
        return {"estado": "credenciales", "tipos": []}
    if resultado != "ok":
        return {"estado": "error", "tipos": [], "error": "No se pudo entrar a Gestión Docente."}

    pagina = _abrir_aplicativo_academico(pagina, notificar) or pagina

    notificar("Abriendo Registro de Notas...")
    if not _abrir_registro_de_notas_en_pagina(pagina, notificar):
        return {"estado": "error", "tipos": [], "error": "El portal no dejó abrir Registro de Notas."}

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

    notificar(f"[OK] Se encontraron {len(tipos)} tipo(s) de nota.")
    return {"estado": "ok", "tipos": tipos, "pagina": pagina}


def obtener_datos_del_curso(curso: dict, notificar=None, cancelado=None, marcar_esperando_token=None) -> dict:
    """Recorre el portal y trae los tipos de nota y la lista de alumnos.

    'curso' es el curso tal como lo guarda el panel ({"codigo", "nombre",
    ...}). La ventana se abre a la vista siempre, sin excepción: el docente
    tiene que escribir el token ahí.

    Después del token siguen dos pasos más: elegir un tipo cualquiera del
    combo para que el portal cargue la lista de alumnos, y quitar el check
    que la trae bloqueada. Los nombres que se leen ahí son con los que
    después se cruzan las notas de Blackboard, así que se guardan junto con
    los tipos.

    Devuelve {"estado": "ok"|"sin_credenciales"|"credenciales"|"error",
    "tipos": [{"valor", "nombre"}], "alumnos": [{"nombre", ...}],
    "error": "..."}.
    """
    notificar = notificar or print
    marcar_esperando_token = marcar_esperando_token or (lambda: None)

    with sync_playwright() as playwright:
        navegador = playwright.chromium.launch(headless=False)
        contexto = navegador.new_context(no_viewport=True)
        try:
            pagina = contexto.new_page()
            recorrido = _llegar_hasta_los_tipos(
                pagina, curso, notificar, cancelado, marcar_esperando_token
            )
            if recorrido["estado"] != "ok":
                return {**recorrido, "alumnos": []}

            pagina = recorrido["pagina"]
            tipos = recorrido["tipos"]
            for tipo in tipos:
                notificar(f"     - {tipo['nombre']}")

            # Con los tipos ya no hace falta el docente: se elige uno
            # cualquiera solo para que el portal muestre la lista de alumnos
            # (son los mismos para todos los tipos).
            alumnos = []
            if elegir_tipo_y_preparar_lista(pagina, tipos[0], notificar):
                alumnos = _leer_alumnos(pagina, notificar)
            if not alumnos:
                notificar("[AVISO] Se guardan los tipos, pero sin la lista de alumnos.")

            return {"estado": "ok", "tipos": tipos, "alumnos": alumnos}
        except Exception as error:
            notificar(f"[ERROR] Ocurrió un problema en Gestión Docente: {error}")
            return {"estado": "error", "tipos": [], "alumnos": [], "error": str(error)}
        finally:
            try:
                navegador.close()
            except Exception:
                pass


def _texto_de_nota(valor) -> str:
    """Cómo se escribe la nota en el campo del portal.

    Los enteros van sin el ".0" que arrastra Python (15.0 -> "15"), porque
    es como el portal muestra las notas; si el cálculo dio decimales se
    dejan tal cual, para no redondear por nuestra cuenta una nota que el
    docente todavía está revisando.
    """
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor)


def escribir_notas_en_portal(
    curso: dict,
    tipo_gd: str,
    notas_por_alumno: dict,
    notificar=None,
    cancelado=None,
    marcar_esperando_token=None,
    al_quedar_listo=None,
) -> dict:
    """Deja escritas en el portal las notas calculadas de un tipo.

    Hace el mismo recorrido de siempre, pero eligiendo en el combo el tipo
    que el docente pidió procesar (no uno cualquiera), y después de quitar
    el check escribe la nota de cada alumno en su casilla.

    IMPORTANTE: no guarda nada. La tarea se da por terminada en cuanto las
    notas quedan escritas ('al_quedar_listo'), pero la VENTANA no se cierra:
    de ahí en adelante es del docente, que revisa lo que quiera y pulsa
    guardar él mismo. Este hilo solo se queda esperando en silencio para
    soltar el navegador cuando él lo cierre.

    'notas_por_alumno' viene con el nombre del alumno tal como lo escribe el
    portal, que es de donde se leyó.

    Devuelve {"estado", "puestas", "sin_nota", "error"}.
    """
    notificar = notificar or print
    marcar_esperando_token = marcar_esperando_token or (lambda: None)
    al_quedar_listo = al_quedar_listo or (lambda resultado: None)

    with sync_playwright() as playwright:
        navegador = playwright.chromium.launch(headless=False)
        contexto = navegador.new_context(no_viewport=True)
        try:
            pagina = contexto.new_page()
            recorrido = _llegar_hasta_los_tipos(
                pagina, curso, notificar, cancelado, marcar_esperando_token
            )
            if recorrido["estado"] != "ok":
                return {**recorrido, "puestas": 0}

            pagina = recorrido["pagina"]

            # El tipo se busca por su nombre entre los que ofrece el portal
            # ahora mismo: el valor guardado podría haber cambiado.
            elegido = next(
                (t for t in recorrido["tipos"] if t["nombre"].strip() == (tipo_gd or "").strip()),
                None,
            )
            if elegido is None:
                error = f'El portal no ofrece el tipo de nota "{tipo_gd}".'
                notificar(f"[AVISO] {error}")
                notificar(f"        Ofrece: {', '.join(t['nombre'] for t in recorrido['tipos'])}")
                return {"estado": "error", "puestas": 0, "error": error}

            if not elegir_tipo_y_preparar_lista(pagina, elegido, notificar):
                return {
                    "estado": "error",
                    "puestas": 0,
                    "error": "No se pudo preparar la lista de alumnos.",
                }

            alumnos = _leer_alumnos(pagina, notificar)
            if not alumnos:
                return {"estado": "error", "puestas": 0, "error": "No se pudo leer la lista de alumnos."}

            # Se emparejan por nombre normalizado: los dos lados salieron de
            # esta misma tabla, pero normalizar cuesta nada y evita que un
            # espacio de más rompa el emparejamiento.
            buscadas = {normalizar_nombre(n): v for n, v in notas_por_alumno.items()}
            pares = []
            sin_nota = []
            for alumno in alumnos:
                valor = buscadas.get(normalizar_nombre(alumno["nombre"]))
                if valor is None or not alumno.get("id_campo_nota"):
                    sin_nota.append(alumno["nombre"])
                    continue
                pares.append({"id": alumno["id_campo_nota"], "valor": _texto_de_nota(valor)})

            notificar(f"Escribiendo {len(pares)} nota(s) en la pantalla...")
            marco = _marco_con_combo(pagina) or pagina
            escrito = marco.evaluate(JS_ESCRIBIR_NOTAS, pares)

            notificar(f"[OK] Quedaron puestas {escrito.get('puestas')} nota(s).")
            if sin_nota:
                notificar(f"[AVISO] {len(sin_nota)} alumno(s) se quedaron sin nota:")
                for nombre in sin_nota[:10]:
                    notificar(f"     - {nombre}")
            notificar("=" * 60)
            notificar("NO se guardó nada: la ventana queda a tu cargo.")
            notificar("Revisa lo que necesites y pulsa guardar tú mismo.")
            notificar("=" * 60)

            resultado = {
                "estado": "ok",
                "puestas": escrito.get("puestas", 0),
                "sin_nota": sin_nota,
            }

            # Para el panel, la tarea termina acá: lo que sigue es trabajo
            # del docente en la ventana, no de la herramienta.
            al_quedar_listo(resultado)

            # De aquí en adelante solo se espera, sin decir nada, a que
            # cierre la ventana: hace falta para poder soltar el navegador,
            # pero ya no es parte de la tarea.
            while not _ventana_cerrada(contexto):
                if cancelado is not None and cancelado():
                    break
                time.sleep(SEGUNDOS_ENTRE_SONDEOS_TOKEN)

            return resultado
        except Exception as error:
            notificar(f"[ERROR] Ocurrió un problema en Gestión Docente: {error}")
            return {"estado": "error", "puestas": 0, "error": str(error)}
        finally:
            try:
                navegador.close()
            except Exception:
                pass


def _ventana_cerrada(contexto) -> bool:
    """True si el docente cerró a mano la ventana del navegador."""
    return not any(not pagina.is_closed() for pagina in contexto.pages)
