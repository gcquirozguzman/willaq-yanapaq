"""
Lee del portal de Gestión Docente los tipos de nota que se pueden registrar
en un curso (T1, T2, EF, RE...).

Este camino es bastante más largo que el de Blackboard, y no se puede
acortar: el portal solo habilita esa lista al final de todo el recorrido.

    1. Entrar al portal con el usuario y la contraseña guardados.
    2. Hacer clic en el aplicativo "Académico" (abre una pestaña nueva).
    3. Ir a la pantalla de Registro de Notas.
    4. Buscar en la tabla la clase del curso elegido y pulsar su
       "Ingresar notas". Un mismo curso suele tener varias clases (una por
       sección), así que antes hay que saber cuál es la de este curso de
       Blackboard (ver _elegir_clase).
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
from willaq.config import URL_GESTION_DOCENTE_REPORTES
from willaq.notas.calculo import normalizar_nombre
from willaq.notas.guardado import obtener_notas_de_curso
from willaq.autenticacion.gestion_docente import (
    SEGUNDOS_ENTRE_PASOS,
    _abrir_aplicativo_academico,
    _abrir_registro_de_notas_en_pagina,
    _entrar_al_portal,
    _esperar_carga_de_pagina,
    _sesion_caducada,
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

# La tabla de clases del docente. Registro de Notas y Reportes usan la misma
# (mismo id y mismas columnas "Semestre", "Clase", "Cód. curso"), solo
# cambia el enlace de cada fila: "Ingresar notas" en una, "Select" en la
# otra. Confirmado con el HTML real de las dos pantallas.
SELECTOR_TABLA_CLASES = "#cphSite_gvClases"

# En Reportes, al elegir una clase aparece este enlace, que abre
# rptNotasGV.aspx con la lista de alumnos de esa clase. A diferencia de
# "Ingresar notas", NO pide token: es la única forma de ver los alumnos de
# una clase antes de decidir cuál abrir.
SELECTOR_ENLACE_REPORTE_NOTAS = "#cphSite_lbtnRepNotas"
SELECTOR_DATOS_DEL_REPORTE = "#cphSite_dvClase"
SELECTOR_TABLA_DEL_REPORTE = "#cphSite_gvReporte"

# Cuántos alumnos tienen que coincidir con los de Blackboard para dar una
# clase por buena, y por cuánto tiene que ganarle a la siguiente. Entre
# clases del mismo curso los alumnos no se repiten (confirmado: la clase
# correcta coincide casi entera y las demás en 0), así que la diferencia
# siempre es enorme; esto solo evita decidir con un empate o con uno suelto.
COINCIDENCIAS_MINIMAS = 3
VECES_QUE_DEBE_GANAR = 2

# Tope de vueltas a todas las páginas de la tabla de clases (ver
# _recorrer_tabla_de_clases): el portal desordena las filas en cada cambio
# de página, así que a veces hace falta más de una vuelta para verlas todas.
VUELTAS_MAXIMAS_TABLA = 4

# Lee la tabla de clases (la página que se esté viendo). Se lee por el
# nombre de cada columna, no por su posición, porque las dos pantallas que
# la usan no tienen las mismas columnas. La tabla viene paginada (10 filas
# por página) y el orden de las filas cambia de una carga a otra, así que
# también se devuelven la página actual y las demás que se pueden pedir.
JS_LEER_CLASES = """
([selector, textoEnlace, clase]) => {
  const tabla = document.querySelector(selector);
  if (!tabla) return null;
  const limpiar = (t) => (t || "")
    .normalize("NFKD")
    .replace(/[\\u0300-\\u036f]/g, "")
    .replace(/\\s+/g, " ")
    .trim()
    .toLowerCase();

  const encabezados = Array.from(tabla.rows[0] ? tabla.rows[0].cells : []).map((c) => limpiar(c.innerText));
  const columna = (nombre) => encabezados.findIndex((e) => e === nombre);
  const iSemestre = columna("semestre");
  const iClase = columna("clase");
  const iCodigo = columna("cod. curso");

  const filas = [];
  const paginas = [];
  let paginaActual = 1;
  let marcado = false;

  for (const fila of Array.from(tabla.rows).slice(1)) {
    // La fila del paginador trae su propia tabla con los números de página:
    // la actual como texto y las demás como enlaces "Page$N".
    const enlacesDePagina = fila.querySelectorAll('a[href*="Page$"]');
    if (fila.cells.length !== encabezados.length) {
      enlacesDePagina.forEach((a) => {
        const n = parseInt((a.getAttribute("href").match(/Page\\$(\\d+)/) || [])[1], 10);
        if (n) paginas.push(n);
      });
      fila.querySelectorAll("span").forEach((s) => {
        const n = parseInt(s.innerText, 10);
        if (n) paginaActual = n;
      });
      continue;
    }

    const celda = (i) => (i >= 0 ? fila.cells[i].innerText.trim() : "");
    const datos = { semestre: celda(iSemestre), clase: celda(iClase), codigo_curso: celda(iCodigo) };
    filas.push(datos);

    // Si se pidió, se marca el enlace de la fila de esa clase para que
    // Playwright lo pulse después por la marca.
    if (clase && datos.clase === clase && !marcado) {
      const enlace = Array.from(fila.querySelectorAll("a, input")).find((c) =>
        limpiar(c.innerText || c.value || "").includes(textoEnlace)
      );
      if (enlace) {
        document.querySelectorAll("[data-willaq-objetivo]").forEach((e) => e.removeAttribute("data-willaq-objetivo"));
        enlace.setAttribute("data-willaq-objetivo", "1");
        marcado = true;
      }
    }
  }
  return { filas, paginas, paginaActual, marcado, columnas: encabezados };
}
"""

# Lee el reporte de notas de una clase: qué clase es (para confirmar que el
# portal abrió la que se pidió) y los nombres de sus alumnos.
JS_LEER_REPORTE = """
([selectorDatos, selectorTabla]) => {
  const limpiar = (t) => (t || "").replace(/\\s+/g, " ").trim();
  let clase = "";
  const datos = document.querySelector(selectorDatos);
  if (datos) {
    for (const fila of Array.from(datos.rows)) {
      if (fila.cells.length >= 2 && limpiar(fila.cells[0].innerText).toLowerCase() === "clase") {
        clase = limpiar(fila.cells[1].innerText);
      }
    }
  }
  const tabla = document.querySelector(selectorTabla);
  if (!tabla || !tabla.rows.length) return { clase, nombres: null };
  const encabezados = Array.from(tabla.rows[0].cells).map((c) => limpiar(c.innerText).toLowerCase());
  const iNombre = encabezados.findIndex((e) => e.includes("nombre"));
  if (iNombre < 0) return { clase, nombres: null };
  const nombres = Array.from(tabla.rows)
    .slice(1)
    .filter((f) => f.cells.length === encabezados.length)
    .map((f) => limpiar(f.cells[iNombre].innerText))
    .filter(Boolean);
  return { clase, nombres };
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


def _codigo_de_asignatura(curso: dict) -> str:
    """El código de la asignatura ("ALED5471"), que es con el que la nombra
    la columna "Cód. curso" de Gestión Docente.

    En Blackboard el curso viene como "CIBERTEC.ALED5471.202607P.30" y
    "ALED5471 INTRODUCCION A LA ALGORITMIA": se toma la primera palabra del
    nombre y, si no la hay, el segundo tramo del código.
    """
    nombre = (curso.get("nombre") or "").strip()
    if nombre:
        return nombre.split()[0].upper()
    tramos = [t.strip() for t in (curso.get("codigo") or "").split(".") if t.strip()]
    return tramos[1].upper() if len(tramos) > 1 else ""


def _seccion_del_curso(curso: dict) -> str:
    """La sección del curso: el último tramo del código de Blackboard."""
    tramos = [t.strip() for t in (curso.get("codigo") or "").split(".") if t.strip()]
    return tramos[-1] if tramos else ""


def _nombres_de_blackboard(curso: dict) -> set:
    """Los alumnos del curso según las notas ya traídas de Blackboard.

    Se juntan los de todas las notas guardadas del curso (normalizados),
    porque son lo único que dice quiénes están en ESTE curso de Blackboard.
    """
    nombres = set()
    for resultado in obtener_notas_de_curso(curso.get("codigo")).values():
        for alumno in resultado.get("alumnos") or []:
            if alumno.get("alumno"):
                nombres.add(normalizar_nombre(alumno["alumno"]))
    return nombres


def _leer_clases(pagina, clase_a_marcar: str = "", texto_enlace: str = ""):
    """Lee la página actual de la tabla de clases (y marca una fila si se pide)."""
    try:
        return pagina.evaluate(JS_LEER_CLASES, [SELECTOR_TABLA_CLASES, texto_enlace, clase_a_marcar])
    except Exception:
        return None


def _ir_a_pagina_de_clases(pagina, numero: int):
    """Pasa a otra página de la tabla de clases (es un postback de ASP.NET)."""
    pagina.click(f'{SELECTOR_TABLA_CLASES} a[href*="Page${numero}"]')
    _esperar_carga_de_pagina(pagina)
    time.sleep(SEGUNDOS_ENTRE_PASOS)


def _ordenar_tabla_de_clases(pagina):
    """Ordena la tabla por la columna "Clase" (su enlace de cabecera).

    Sin ordenar, el portal entrega las filas en un orden distinto en cada
    postback, y al pasar de página se repiten unas y se pierden otras
    (confirmado en vivo). Ordenada, cada página trae siempre las mismas.
    """
    enlace = pagina.locator(f'{SELECTOR_TABLA_CLASES} a[href*="Sort$S_CLA_CODIGO"]')
    try:
        if enlace.count():
            enlace.first.click()
            _esperar_carga_de_pagina(pagina)
            time.sleep(SEGUNDOS_ENTRE_PASOS)
    except Exception:
        pass


def _recorrer_tabla_de_clases(pagina, clase_a_marcar: str = "", texto_enlace: str = ""):
    """Recorre todas las páginas de la tabla de clases.

    Sin 'clase_a_marcar', devuelve todas las filas de todas las páginas.
    Con ella, se detiene en la página donde está esa clase, le deja marcado
    el enlace 'texto_enlace' y devuelve True (o False si no está en
    ninguna). Hace falta recorrerlas porque la tabla trae 10 filas por
    página y el portal no las ordena siempre igual: la clase buscada puede
    caer en cualquiera.
    """
    # Además, el portal desordena las filas con cada cambio de página
    # (confirmado: una misma clase sale en la página 1 y en la 2, y otra no
    # sale en ninguna). Por eso primero se ordena la tabla y, por si acaso,
    # se dan vueltas hasta que una vuelta entera ya no traiga clases nuevas.
    _ordenar_tabla_de_clases(pagina)
    todas = {}
    for vuelta in range(VUELTAS_MAXIMAS_TABLA):
        nuevas = 0
        visitadas = set()
        paginado = False
        while True:
            leido = _leer_clases(pagina, clase_a_marcar, texto_enlace)
            if not leido:
                return False if clase_a_marcar else list(todas.values())
            if clase_a_marcar and leido.get("marcado"):
                return True
            for fila in leido.get("filas") or []:
                if fila["clase"] and fila["clase"] not in todas:
                    todas[fila["clase"]] = fila
                    nuevas += 1
            visitadas.add(leido.get("paginaActual"))
            paginado = paginado or bool(leido.get("paginas"))
            pendientes = [n for n in leido.get("paginas") or [] if n not in visitadas]
            if not pendientes:
                break
            _ir_a_pagina_de_clases(pagina, pendientes[0])
        # Buscando una clase concreta se aprovechan todas las vueltas: que
        # no haya clases nuevas no quiere decir que ya pasó por delante.
        if not paginado or (not clase_a_marcar and vuelta > 0 and nuevas == 0):
            break
    return False if clase_a_marcar else list(todas.values())


def _alumnos_del_reporte(pagina, clase: str, notificar):
    """Los alumnos de una clase según su "Reporte de notas" (no pide token).

    Devuelve un set de nombres normalizados, o None si no se pudo leer.
    """
    time.sleep(SEGUNDOS_ENTRE_PASOS)
    try:
        pagina.goto(URL_GESTION_DOCENTE_REPORTES, wait_until="domcontentloaded", timeout=60_000)
    except Exception as error:
        notificar(f"[AVISO] No se pudo abrir Reportes: {error}")
        return None
    _esperar_carga_de_pagina(pagina)
    time.sleep(SEGUNDOS_ENTRE_PASOS)
    if _sesion_caducada(pagina):
        notificar("[AVISO] El portal cerró la sesión al abrir Reportes.")
        return None

    if not _recorrer_tabla_de_clases(pagina, clase, "select"):
        notificar(f"[AVISO] La clase {clase} no aparece en Reportes.")
        return None
    pagina.click('[data-willaq-objetivo="1"]')
    _esperar_carga_de_pagina(pagina)
    time.sleep(SEGUNDOS_ENTRE_PASOS)

    try:
        pagina.click(SELECTOR_ENLACE_REPORTE_NOTAS, timeout=15_000)
        pagina.wait_for_selector(SELECTOR_TABLA_DEL_REPORTE, timeout=30_000)
    except Exception as error:
        notificar(f"[AVISO] No se pudo abrir el reporte de la clase {clase}: {error}")
        return None
    _esperar_carga_de_pagina(pagina)

    leido = pagina.evaluate(JS_LEER_REPORTE, [SELECTOR_DATOS_DEL_REPORTE, SELECTOR_TABLA_DEL_REPORTE])
    # Se confirma que el reporte es de la clase pedida: si el portal hubiera
    # abierto otra, comparar sus alumnos llevaría justo al error que esto
    # viene a evitar.
    if leido.get("clase") != clase or leido.get("nombres") is None:
        notificar(f"[AVISO] El reporte abierto no es el de la clase {clase} (dice {leido.get('clase') or '?'}).")
        return None
    return {normalizar_nombre(n) for n in leido["nombres"]}


def _elegir_por_alumnos(pagina, curso: dict, clases: list, notificar) -> str:
    """Elige, entre varias clases, la que tiene los alumnos de este curso.

    Es el último recurso, para cuando el código de Blackboard no dice nada
    de la clase (pasa, por ejemplo, con "CIBERTEC.GDAT5463.202609202611.
    LX4353XK913"). Compara los alumnos del reporte de cada clase con los de
    las notas ya traídas de Blackboard. Devuelve "" si no hay un ganador
    claro: en ese caso es mejor parar que abrir una clase que no es.
    """
    nombres_bb = _nombres_de_blackboard(curso)
    if not nombres_bb:
        notificar("[AVISO] Para saber cuál es tu clase necesito los alumnos del curso en Blackboard.")
        notificar('        Usa primero "Obtener Notas Blackboard" en este curso y vuelve a intentarlo.')
        return ""

    notificar(f"Comparando los alumnos de cada clase con los {len(nombres_bb)} de Blackboard...")
    coincidencias = {}
    for clase in clases:
        nombres = _alumnos_del_reporte(pagina, clase, notificar)
        if nombres is None:
            return ""
        coincidencias[clase] = len(nombres & nombres_bb)
        notificar(f"     Clase {clase}: {coincidencias[clase]} de {len(nombres)} alumnos coinciden.")

    ordenadas = sorted(coincidencias.items(), key=lambda par: par[1], reverse=True)
    mejor, cuantos = ordenadas[0]
    siguiente = ordenadas[1][1] if len(ordenadas) > 1 else 0
    if cuantos < COINCIDENCIAS_MINIMAS or cuantos < siguiente * VECES_QUE_DEBE_GANAR:
        notificar("[AVISO] Ninguna clase coincide con claridad con los alumnos de Blackboard.")
        return ""
    return mejor


def _elegir_clase(pagina, curso: dict, candidatas: list, notificar) -> str:
    """Decide cuál de las clases de Gestión Docente es este curso.

    Un mismo curso (GDAT5463, IGER5353...) suele tener varias clases en el
    portal, una por sección. De la más barata a la más cara:

    1. La clase que ya se identificó antes para este curso (se guarda).
    2. Si solo hay una, esa.
    3. La que es exactamente semestre + sección de Blackboard: la clase
       2026532937 es el semestre 202653 más la sección 2937 de
       "CIBERTEC.IGER5353.202609P.2937".
    4. La que tiene los mismos alumnos que el curso en Blackboard.

    Nunca se elige "la primera": el portal no las ordena siempre igual.
    Devuelve "" si no se pudo saber.
    """
    clases = [c["clase"] for c in candidatas]

    guardada = curso.get("clase_gd")
    if guardada in clases:
        notificar(f"Usando la clase ya identificada antes: {guardada}")
        return guardada

    if len(clases) == 1:
        return clases[0]

    seccion = _seccion_del_curso(curso)
    exactas = [c["clase"] for c in candidatas if seccion and c["clase"] == c["semestre"] + seccion]
    if len(exactas) == 1:
        notificar(f"La clase {exactas[0]} corresponde a la sección {seccion}.")
        return exactas[0]

    return _elegir_por_alumnos(pagina, curso, clases, notificar)


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

    codigo = _codigo_de_asignatura(curso)
    if not codigo:
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

    notificar(f"Buscando el curso {codigo} en la tabla...")
    time.sleep(SEGUNDOS_ENTRE_PASOS)
    candidatas = [
        fila
        for fila in _recorrer_tabla_de_clases(pagina)
        if fila["codigo_curso"].upper() == codigo
    ]
    if not candidatas:
        error = f"No se encontró el curso {codigo} en Registro de Notas."
        notificar(f"[AVISO] {error}")
        return {"estado": "error", "tipos": [], "error": error}
    if len(candidatas) > 1:
        notificar(f"Hay {len(candidatas)} clases de {codigo}: {', '.join(c['clase'] for c in candidatas)}")

    clase = _elegir_clase(pagina, curso, candidatas, notificar)
    if not clase:
        error = f"No se pudo saber cuál de las clases de {codigo} es este curso."
        notificar(f"[AVISO] {error}")
        return {"estado": "error", "tipos": [], "error": error}

    # Comparar alumnos obliga a pasar por Reportes: se vuelve a Registro de
    # Notas para abrir la clase elegida.
    if "regnotas" not in (pagina.url or "").lower():
        notificar("Volviendo a Registro de Notas...")
        if not _abrir_registro_de_notas_en_pagina(pagina, notificar):
            return {"estado": "error", "tipos": [], "error": "El portal no dejó volver a Registro de Notas."}

    if not _recorrer_tabla_de_clases(pagina, clase, "ingresar"):
        error = f'No se encontró el botón "Ingresar notas" de la clase {clase}.'
        notificar(f"[AVISO] {error}")
        return {"estado": "error", "tipos": [], "error": error}

    notificar(f"[OK] Clase elegida: {clase}")
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
    return {"estado": "ok", "tipos": tipos, "pagina": pagina, "clase": clase}


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

            return {"estado": "ok", "tipos": tipos, "alumnos": alumnos, "clase": recorrido["clase"]}
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
