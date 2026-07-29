// Panel web de Willaq Yanapaq: solo usa fetch + sondeo (polling) periódico,
// sin frameworks ni paso de "build".

// --- Tema claro/oscuro ---

const CLAVE_TEMA = "willaq-tema";
const botonTema = document.getElementById("boton-tema");

function aplicarTema(tema) {
  document.documentElement.setAttribute("data-tema", tema);
  botonTema.textContent = tema === "oscuro" ? "Modo claro" : "Modo oscuro";
}

function alternarTema() {
  const actual = document.documentElement.getAttribute("data-tema");
  const nuevo = actual === "oscuro" ? "claro" : "oscuro";
  localStorage.setItem(CLAVE_TEMA, nuevo);
  aplicarTema(nuevo);
}

(function iniciarTema() {
  const guardado = localStorage.getItem(CLAVE_TEMA);
  if (guardado) {
    aplicarTema(guardado);
  } else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    aplicarTema("oscuro");
  } else {
    aplicarTema("claro");
  }
})();

botonTema.addEventListener("click", alternarTema);

// --- Login ---

const botonIniciarLogin = document.getElementById("boton-iniciar-login");
const botonConfirmarLoginManual = document.getElementById("boton-confirmar-login-manual");
const botonConfirmarCierre = document.getElementById("boton-confirmar-cierre");
const registroLogin = document.getElementById("registro-login");
const puntoEstado = document.getElementById("punto-estado");
const tituloEstado = document.getElementById("titulo-estado");
const descripcionEstado = document.getElementById("descripcion-estado");
const etiquetaEstadoLogin = document.getElementById("etiqueta-estado-login");
const identidadDocente = document.getElementById("identidad-docente");
const avatarDocente = document.getElementById("avatar-docente");
const nombreDocenteEl = document.getElementById("nombre-docente");
const tarjetaSesion = document.getElementById("tarjeta-sesion");
const cargando = document.getElementById("cargando");
const textoCargando = document.getElementById("texto-cargando");
const itemPlantilla = document.getElementById("item-plantilla");
const estadoPlantilla = document.getElementById("estado-plantilla");
const botonGenerarPlantilla = document.getElementById("boton-generar-plantilla");
const botonVerAnuncios = document.getElementById("boton-ver-anuncios");
const itemCursos = document.getElementById("item-cursos");
const estadoCursosEl = document.getElementById("estado-cursos");
const botonObtenerCursos = document.getElementById("boton-obtener-cursos");

let intervaloConsultaLogin = null;

// Textos e íconos según la fase/resultado del login, para no repetir la
// lógica en cada lugar donde se actualiza la interfaz.
const TEXTOS_ESTADO = {
  inactivo: {
    clase: "",
    titulo: "INACTIVO",
    descripcion: 'Presiona "Iniciar sesión" para abrir Blackboard y verificar tu acceso.',
    etiqueta: "Inactivo",
  },
  ejecutando: {
    clase: "en-proceso",
    titulo: "EN PROCESO",
    descripcion: "Abriendo el navegador y verificando tu sesión con Blackboard...",
    etiqueta: "En proceso",
  },
  esperando_login_manual: {
    clase: "en-proceso",
    titulo: "ESPERANDO LOGIN MANUAL",
    descripcion:
      "Completa tu usuario, clave y el código SMS en la ventana del navegador. " +
      'Cuando termines, presiona "Ya completé el login, continuar".',
    etiqueta: "Esperando MFA",
  },
  ok: {
    clase: "ok",
    titulo: "SESIÓN LISTA",
    descripcion: "Tu sesión quedó guardada. Puedes cerrar el navegador cuando quieras.",
    etiqueta: "Activo",
  },
  aviso: {
    clase: "aviso",
    titulo: "REVISA EL NAVEGADOR",
    descripcion: "No se pudo confirmar el login. Revisa la ventana del navegador antes de cerrarla.",
    etiqueta: "Aviso",
  },
  error: {
    clase: "error",
    titulo: "OCURRIÓ UN ERROR",
    descripcion: "Algo falló durante el login. Revisa el registro de abajo para más detalles.",
    etiqueta: "Error",
  },
};

function detectarResultadoDesdeLogs(logs) {
  const texto = logs.join("\n");
  if (texto.includes("[ERROR]")) return "error";
  if (texto.includes("[AVISO]")) return "aviso";
  if (texto.includes("[OK]")) return "ok";
  return null;
}

function actualizarHeroDeEstado(estado) {
  let clave = estado.fase;

  if (estado.fase === "esperando_cierre" || estado.fase === "terminado") {
    clave = detectarResultadoDesdeLogs(estado.logs) || "ok";
  }

  const textos = TEXTOS_ESTADO[clave] || TEXTOS_ESTADO.inactivo;

  puntoEstado.className = "punto-estado " + textos.clase;
  tituloEstado.className = "titulo-hero " + textos.clase;
  tituloEstado.textContent = textos.titulo;
  descripcionEstado.textContent = textos.descripcion;
  etiquetaEstadoLogin.textContent = textos.etiqueta;
}

async function iniciarLogin() {
  botonIniciarLogin.disabled = true;
  registroLogin.textContent = "";

  const respuesta = await fetch("/api/login/iniciar", { method: "POST" });
  if (!respuesta.ok) {
    const datos = await respuesta.json();
    alert(datos.error || "No se pudo iniciar el login.");
    botonIniciarLogin.disabled = false;
    return;
  }

  intervaloConsultaLogin = setInterval(consultarEstadoLogin, 1000);
}

async function consultarEstadoLogin() {
  const respuesta = await fetch("/api/login/estado");
  const estado = await respuesta.json();

  registroLogin.textContent = estado.logs.join("\n");
  registroLogin.scrollTop = registroLogin.scrollHeight;

  const sesionActiva = estado.fase === "terminado" && (estado.resultado === "ok" || estado.resultado === "activa");

  actualizarHeroDeEstado(estado);
  actualizarCargando(estado);
  actualizarIdentidadDocente(estado, sesionActiva);
  actualizarBloqueoHerramientas(sesionActiva);

  botonConfirmarLoginManual.classList.toggle("oculto", estado.fase !== "esperando_login_manual");
  botonConfirmarCierre.classList.toggle("oculto", estado.fase !== "esperando_cierre");

  if (estado.fase === "terminado") {
    clearInterval(intervaloConsultaLogin);
    botonIniciarLogin.disabled = false;
  }
}

function actualizarCargando(estado) {
  // El log técnico sigue disponible (colapsado, ver "detalles técnicos"),
  // pero para el docente el indicador principal mientras algo corre es
  // este loader, no el texto crudo del log.
  cargando.classList.toggle("oculto", !estado.en_progreso);
  if (estado.fase === "esperando_login_manual") {
    textoCargando.textContent = "Esperando que completes el login en el navegador...";
  } else {
    textoCargando.textContent = "Esto puede tardar unos segundos...";
  }
}

function actualizarIdentidadDocente(estado, sesionActiva) {
  tarjetaSesion.classList.toggle("oculto", !sesionActiva);

  if (sesionActiva && estado.nombre_docente) {
    nombreDocenteEl.textContent = estado.nombre_docente;
    identidadDocente.classList.remove("oculto");
  } else {
    identidadDocente.classList.add("oculto");
  }

  if (sesionActiva && estado.tiene_avatar) {
    avatarDocente.src = "/api/avatar?t=" + Date.now();
    avatarDocente.classList.remove("oculto");
  } else {
    avatarDocente.classList.add("oculto");
  }
}

// Lista de cursos activos obtenida en esta sesión del navegador (se llena
// cuando "Obtener Cursos Activos" termina con éxito). "Generar Anuncios
// Semanales" se desbloquea en base a esto, no solo con tener sesión.
let cursosObtenidos = [];

function actualizarBloqueoHerramientas(sesionActiva) {
  botonObtenerCursos.disabled = !sesionActiva;
  itemCursos.classList.toggle("bloqueada", !sesionActiva);
  if (!sesionActiva) {
    estadoCursosEl.textContent = "Inicia sesión primero";
  } else if (estadoCursosEl.textContent === "Inicia sesión primero") {
    estadoCursosEl.textContent = "Disponible";
  }

  actualizarBloqueoPlantilla();
}

function actualizarBloqueoPlantilla() {
  const hayCursos = cursosObtenidos.length > 0;
  botonGenerarPlantilla.disabled = !hayCursos;
  itemPlantilla.classList.toggle("bloqueada", !hayCursos);
  estadoPlantilla.textContent = hayCursos ? "Disponible" : "Obtén tus cursos primero";
}

// Consulta el estado una vez al cargar la página, por si ya se había hecho
// login antes (por ejemplo, si recargas el panel sin cerrarlo).
consultarEstadoLogin();
consultarEstadoCursos();

async function confirmarLoginManual() {
  botonConfirmarLoginManual.disabled = true;
  await fetch("/api/login/confirmar-login-manual", { method: "POST" });
  botonConfirmarLoginManual.disabled = false;
}

async function confirmarCierre() {
  botonConfirmarCierre.disabled = true;
  await fetch("/api/login/confirmar-cierre", { method: "POST" });
}

botonIniciarLogin.addEventListener("click", iniciarLogin);
botonConfirmarLoginManual.addEventListener("click", confirmarLoginManual);
botonConfirmarCierre.addEventListener("click", confirmarCierre);

// --- Generar Anuncios Semanales ---
// Por ahora, este asistente solo junta los datos y los guarda (ver
// willaq/anuncios/semanal.py); calcular las fechas de cada semana y
// generar el Excel es un paso futuro.

const dialogoAnuncios = document.getElementById("dialogo-anuncios-semanales");
const campoCurso = document.getElementById("campo-curso");
const campoFechaInicio = document.getElementById("campo-fecha-inicio");
const campoFechaFin = document.getElementById("campo-fecha-fin");
const campoDiaInicio = document.getElementById("campo-dia-inicio");
const campoHoraInicio = document.getElementById("campo-hora-inicio");
const campoDiaFin = document.getElementById("campo-dia-fin");
const campoHoraFin = document.getElementById("campo-hora-fin");
const mensajeAsistenteAnuncios = document.getElementById("mensaje-asistente-anuncios");
const botonGuardarAnuncios = document.getElementById("boton-guardar-anuncios-semanales");
const botonCancelarAnuncios = document.getElementById("boton-cancelar-anuncios-semanales");
const campoConfirmarFechaPasada = document.getElementById("campo-confirmar-fecha-pasada");
const casillaConfirmarFechaPasada = document.getElementById("casilla-confirmar-fecha-pasada");
const casillaEliminarAnunciosExistentes = document.getElementById("casilla-eliminar-anuncios-existentes");
const dialogoGuardadoOk = document.getElementById("dialogo-guardado-ok");
const botonCerrarGuardadoOk = document.getElementById("boton-cerrar-guardado-ok");

const DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
const CAMPOS_REQUERIDOS_ANUNCIOS = [
  "curso_codigo",
  "curso_nombre",
  "fecha_inicio_curso",
  "fecha_fin_curso",
  "dia_inicio_semana",
  "hora_inicio_semana",
  "dia_fin_semana",
  "hora_fin_semana",
];

// Fecha de hoy en formato YYYY-MM-DD, en hora local (no UTC, para que no se
// corra un día según el huso horario del docente).
function fechaHoyISO() {
  const ahora = new Date();
  const local = new Date(ahora.getTime() - ahora.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

// La casilla "igual deseo agregar anuncios..." solo tiene sentido (y solo se
// muestra) cuando la fecha de inicio elegida ya pasó.
function actualizarVisibilidadCasillaFechaPasada() {
  const fechaPasada = Boolean(campoFechaInicio.value) && campoFechaInicio.value < fechaHoyISO();
  campoConfirmarFechaPasada.classList.toggle("oculto", !fechaPasada);
  if (!fechaPasada) {
    casillaConfirmarFechaPasada.checked = false;
  }
}

campoFechaInicio.addEventListener("change", actualizarVisibilidadCasillaFechaPasada);

function llenarSelectDeDias(select) {
  select.innerHTML = "";
  for (const dia of DIAS_SEMANA) {
    const opcion = document.createElement("option");
    opcion.value = dia.toLowerCase();
    opcion.textContent = dia;
    select.appendChild(opcion);
  }
}

llenarSelectDeDias(campoDiaInicio);
llenarSelectDeDias(campoDiaFin);

// Trae la configuración ya guardada de este curso (si existe) y llena el
// formulario con ella, para que el docente no tenga que volver a escribir
// todo si ya había configurado este curso antes. Si no hay nada guardado,
// deja el formulario en blanco (con el primer día de la semana por defecto).
//
// Si ya había una configuración guardada, "Ver anuncios" se habilita de
// una vez: no hace falta volver a darle "Guardar" solo para poder verla.
async function precargarConfiguracionGuardada(codigoCurso) {
  mensajeAsistenteAnuncios.textContent = "";

  let configuracion = null;
  if (codigoCurso) {
    const respuesta = await fetch(`/api/anuncios-semanales/${encodeURIComponent(codigoCurso)}`);
    const datos = await respuesta.json();
    if (datos && datos.curso_codigo) {
      configuracion = datos;
    }
  }

  campoFechaInicio.value = configuracion ? configuracion.fecha_inicio_curso : "";
  campoFechaFin.value = configuracion ? configuracion.fecha_fin_curso : "";
  campoDiaInicio.value = configuracion ? configuracion.dia_inicio_semana : campoDiaInicio.options[0].value;
  campoHoraInicio.value = configuracion ? configuracion.hora_inicio_semana : "";
  campoDiaFin.value = configuracion ? configuracion.dia_fin_semana : campoDiaFin.options[0].value;
  campoHoraFin.value = configuracion ? configuracion.hora_fin_semana : "";
  casillaConfirmarFechaPasada.checked = configuracion ? Boolean(configuracion.confirmar_fecha_pasada) : false;
  casillaEliminarAnunciosExistentes.checked = configuracion ? Boolean(configuracion.eliminar_anuncios_existentes) : false;

  actualizarVisibilidadCasillaFechaPasada();

  if (configuracion) {
    configuracionAnunciosActual = configuracion;
    botonVerAnuncios.disabled = false;
  }
}

function abrirAsistenteAnuncios() {
  campoCurso.innerHTML = "";
  for (const curso of cursosObtenidos) {
    const opcion = document.createElement("option");
    opcion.value = curso.codigo;
    opcion.textContent = curso.nombre;
    campoCurso.appendChild(opcion);
  }

  mensajeAsistenteAnuncios.textContent = "";
  botonVerAnuncios.disabled = true;
  precargarConfiguracionGuardada(campoCurso.value);
  dialogoAnuncios.showModal();
}

campoCurso.addEventListener("change", () => {
  botonVerAnuncios.disabled = true;
  precargarConfiguracionGuardada(campoCurso.value);
});

async function guardarAnunciosSemanales() {
  const cursoSeleccionado = cursosObtenidos.find((curso) => curso.codigo === campoCurso.value);

  const datos = {
    curso_codigo: campoCurso.value,
    curso_nombre: cursoSeleccionado ? cursoSeleccionado.nombre : "",
    fecha_inicio_curso: campoFechaInicio.value,
    fecha_fin_curso: campoFechaFin.value,
    dia_inicio_semana: campoDiaInicio.value,
    hora_inicio_semana: campoHoraInicio.value,
    dia_fin_semana: campoDiaFin.value,
    hora_fin_semana: campoHoraFin.value,
    confirmar_fecha_pasada: casillaConfirmarFechaPasada.checked,
    eliminar_anuncios_existentes: casillaEliminarAnunciosExistentes.checked,
  };

  const faltaAlgo = CAMPOS_REQUERIDOS_ANUNCIOS.some((campo) => !datos[campo]);
  if (faltaAlgo) {
    mensajeAsistenteAnuncios.textContent = "Completa todos los campos antes de guardar.";
    return;
  }

  if (datos.fecha_inicio_curso >= datos.fecha_fin_curso) {
    mensajeAsistenteAnuncios.textContent = "La fecha de inicio del curso debe ser anterior a la fecha de fin.";
    return;
  }

  if (datos.dia_inicio_semana === datos.dia_fin_semana) {
    mensajeAsistenteAnuncios.textContent = "El día de inicio y el día de fin de semana no pueden ser el mismo.";
    return;
  }

  const indiceInicio = DIAS_SEMANA.findIndex((dia) => dia.toLowerCase() === datos.dia_inicio_semana);
  const indiceFin = DIAS_SEMANA.findIndex((dia) => dia.toLowerCase() === datos.dia_fin_semana);
  if (indiceInicio >= indiceFin) {
    mensajeAsistenteAnuncios.textContent =
      "El día de anuncio de inicio de semana debe ser antes que el día de anuncio de fin de semana.";
    return;
  }

  botonGuardarAnuncios.disabled = true;
  const respuesta = await fetch("/api/anuncios-semanales/guardar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(datos),
  });
  const resultado = await respuesta.json();
  botonGuardarAnuncios.disabled = false;

  if (resultado.estado !== "ok") {
    mensajeAsistenteAnuncios.textContent = resultado.error || "No se pudo guardar la configuración.";
    return;
  }

  mensajeAsistenteAnuncios.textContent = "";
  configuracionAnunciosActual = datos;
  botonVerAnuncios.disabled = false;
  dialogoGuardadoOk.showModal();
}

botonCerrarGuardadoOk.addEventListener("click", () => dialogoGuardadoOk.close());

botonGenerarPlantilla.addEventListener("click", abrirAsistenteAnuncios);
botonGuardarAnuncios.addEventListener("click", guardarAnunciosSemanales);
botonCancelarAnuncios.addEventListener("click", () => dialogoAnuncios.close());

// --- Ver anuncios (grilla generada a partir de lo guardado) ---
// Por ahora el mensaje es de relleno (aleatorio); fecha, hora y semanas se
// calculan de verdad a partir de la última configuración guardada en el
// asistente. Cada clic en "Ver anuncios" vuelve a generar la grilla desde
// cero, así que si se guarda una configuración distinta, se refleja sola.

const dialogoVerAnuncios = document.getElementById("dialogo-ver-anuncios");
const cuerpoTablaAnuncios = document.getElementById("cuerpo-tabla-anuncios");
const botonCerrarVerAnuncios = document.getElementById("boton-cerrar-ver-anuncios");

// Última configuración guardada con éxito en el asistente (ver
// guardarAnunciosSemanales); "Ver anuncios" solo se habilita después de
// guardar, así que siempre habrá algo aquí cuando se pueda hacer clic.
let configuracionAnunciosActual = null;

// Base de 20 mensajes de relleno para "Inicio" y 20 para "Fin", uno por
// cada semana ordinal del curso (1ra a 20va). Se usan en orden según el
// número real de semana: si el curso tiene 10 semanas, se usan las
// primeras 10 de esta base.
const ORDINALES_SEMANA = [
  "Primera", "Segunda", "Tercera", "Cuarta", "Quinta",
  "Sexta", "Séptima", "Octava", "Novena", "Décima",
  "Undécima", "Duodécima", "Decimotercera", "Decimocuarta", "Decimoquinta",
  "Decimosexta", "Decimoséptima", "Decimoctava", "Decimonovena", "Vigésima",
];

function generarMensajeInicio(indice) {
  const ordinal = ORDINALES_SEMANA[indice];
  const introduccion =
    indice === 0
      ? "Damos inicio a nuestro proceso de aprendizaje, sentando las bases y los conceptos fundamentales que serán el punto de partida para todo lo que iremos construyendo en las próximas semanas."
      : `Continuamos avanzando en nuestro proceso de aprendizaje, fortaleciendo los conocimientos adquiridos en la ${ORDINALES_SEMANA[indice - 1].toLowerCase()} semana e incorporando nuevos conceptos que serán fundamentales para su formación.`;

  return `Tema: Inicio de la ${ordinal} Semana

¡Bienvenid@s a la ${ordinal.toLowerCase()} semana del curso! 👋✨
${introduccion} 📚💡 Cada sesión les permitirá desarrollar nuevas habilidades mediante la práctica y la resolución de ejercicios aplicados.

Los invito a seguir participando activamente, plantear sus dudas y mantener el entusiasmo por aprender. Con constancia y dedicación, cada semana será una oportunidad para seguir creciendo. ¡Vamos por más! 🚀

Saludos,
Profesor Gian Carlo Quiroz`;
}

function generarMensajeFin(indice) {
  const ordinal = ORDINALES_SEMANA[indice];

  return `Tema: Conclusiones de la ${ordinal} Semana

¡Felicitaciones por el trabajo realizado esta semana! 👏✨
Han continuado fortaleciendo sus conocimientos y desarrollando nuevas habilidades que les permitirán afrontar los siguientes temas con mayor seguridad. Cada ejercicio y actividad realizada representa un paso importante en su proceso de aprendizaje. 📖💪

Los animo a repasar lo trabajado durante la semana y a seguir practicando. La constancia es la clave para lograr excelentes resultados. ¡Nos vemos en la siguiente sesión con nuevos retos y aprendizajes! 🚀

Saludos,
Profesor Gian Carlo Quiroz`;
}

const MENSAJES_INICIO_SEMANA = ORDINALES_SEMANA.map((_, indice) => generarMensajeInicio(indice));
const MENSAJES_FIN_SEMANA = ORDINALES_SEMANA.map((_, indice) => generarMensajeFin(indice));

// Título corto del anuncio, según el formato pedido.
function tituloAnuncio(tipo, numeroSemana) {
  return tipo === "Inicio" ? `INICIO SEMANA ${numeroSemana} 🚀🌐` : `CIERRE DE SEMANA ${numeroSemana} ✅🎉`;
}

// Mensaje de la base (20 para inicio, 20 para fin), usado en orden según el
// número real de semana del curso; si el curso tiene más de 20 semanas, se
// vuelve a empezar desde la primera de la base.
function mensajeDeLaBase(tipo, numeroSemana) {
  const lista = tipo === "Inicio" ? MENSAJES_INICIO_SEMANA : MENSAJES_FIN_SEMANA;
  return lista[(numeroSemana - 1) % lista.length];
}

// Índice del día (lunes=0 ... domingo=6) de una fecha "YYYY-MM-DD", tratada
// como fecha local (no UTC) para que no se corra un día.
function indiceDiaSemana(fechaISO) {
  const [anio, mes, dia] = fechaISO.split("-").map(Number);
  const fecha = new Date(anio, mes - 1, dia);
  return (fecha.getDay() + 6) % 7;
}

function sumarDias(fechaISO, dias) {
  const [anio, mes, dia] = fechaISO.split("-").map(Number);
  const fecha = new Date(anio, mes - 1, dia);
  fecha.setDate(fecha.getDate() + dias);
  const y = fecha.getFullYear();
  const m = String(fecha.getMonth() + 1).padStart(2, "0");
  const d = String(fecha.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

// Arma una fila "Inicio" y una "Fin" por cada semana entre fecha_inicio_curso
// y fecha_fin_curso, usando los días/horas elegidos en el asistente.
//
// Por defecto, se omite cada anuncio individual cuya fecha ya pasó (no la
// semana completa): por ejemplo, si el "inicio de semana" ya pasó pero el
// "fin de semana" todavía no, se muestra solo el de fin. Se empieza a
// mostrar desde el próximo anuncio disponible (>= hoy). Si se marcó
// "regularizar" (confirmar_fecha_pasada), se muestran todos, incluidos los
// que ya pasaron, desde la fecha real de inicio del curso.
function generarFilasAnuncios(configuracion) {
  const indiceInicio = DIAS_SEMANA.findIndex((dia) => dia.toLowerCase() === configuracion.dia_inicio_semana);
  const indiceFin = DIAS_SEMANA.findIndex((dia) => dia.toLowerCase() === configuracion.dia_fin_semana);
  const desfaseFin = indiceFin - indiceInicio;

  // Primera fecha en la que cae el día de "inicio de semana", a partir del
  // inicio real del curso (puede ser esa misma fecha, o unos días después).
  const desfaseHastaPrimerInicio = (indiceInicio - indiceDiaSemana(configuracion.fecha_inicio_curso) + 7) % 7;
  let fechaInicioSemana = sumarDias(configuracion.fecha_inicio_curso, desfaseHastaPrimerInicio);

  const hoy = fechaHoyISO();
  const filas = [];
  let numeroSemana = 1;
  let nro = 1;

  while (fechaInicioSemana <= configuracion.fecha_fin_curso) {
    const fechaFinSemana = sumarDias(fechaInicioSemana, desfaseFin);

    if (configuracion.confirmar_fecha_pasada || fechaInicioSemana >= hoy) {
      filas.push({
        nro: nro++,
        semana: `Semana ${numeroSemana}`,
        tipo: "Inicio",
        titulo: tituloAnuncio("Inicio", numeroSemana),
        mensaje: mensajeDeLaBase("Inicio", numeroSemana),
        fecha: fechaInicioSemana,
        hora: configuracion.hora_inicio_semana,
      });
    }

    if (configuracion.confirmar_fecha_pasada || fechaFinSemana >= hoy) {
      filas.push({
        nro: nro++,
        semana: `Semana ${numeroSemana}`,
        tipo: "Fin",
        titulo: tituloAnuncio("Fin", numeroSemana),
        mensaje: mensajeDeLaBase("Fin", numeroSemana),
        fecha: fechaFinSemana,
        hora: configuracion.hora_fin_semana,
      });
    }

    numeroSemana += 1;
    fechaInicioSemana = sumarDias(fechaInicioSemana, 7);
  }

  return filas;
}

function crearCeldaEditable(valor, tipo) {
  const input = document.createElement("input");
  input.type = tipo;
  input.value = valor;
  input.className = "celda-editable";
  return input;
}

function crearAreaEditable(valor) {
  const area = document.createElement("textarea");
  area.value = valor;
  area.className = "celda-editable celda-editable-area";
  area.rows = 8;
  return area;
}

// Fila oculta por defecto, con el título y el mensaje completos (editables)
// de un anuncio. Se muestra/oculta al hacer clic en el botón ▶ de su fila
// principal, así la tabla se mantiene compacta pero el texto largo se puede
// leer y editar sin recortes.
function crearFilaDetalle(anuncio) {
  const fila = document.createElement("tr");
  fila.className = "fila-detalle oculto";

  const celda = document.createElement("td");
  celda.colSpan = 6;

  const contenedor = document.createElement("div");
  contenedor.className = "detalle-anuncio";

  const campoTitulo = document.createElement("label");
  campoTitulo.className = "detalle-campo";
  campoTitulo.append("Título", crearCeldaEditable(anuncio.titulo, "text"));

  const campoMensaje = document.createElement("label");
  campoMensaje.className = "detalle-campo";
  campoMensaje.append("Mensaje", crearAreaEditable(anuncio.mensaje));

  contenedor.append(campoTitulo, campoMensaje);
  celda.appendChild(contenedor);
  fila.appendChild(celda);

  return fila;
}

function abrirVistaAnuncios() {
  cuerpoTablaAnuncios.innerHTML = "";

  if (!configuracionAnunciosActual) {
    return;
  }

  const filas = generarFilasAnuncios(configuracionAnunciosActual);

  if (filas.length === 0) {
    const fila = document.createElement("tr");
    const celda = document.createElement("td");
    celda.colSpan = 6;
    celda.textContent = "No hay semanas completas dentro del rango de fechas del curso.";
    fila.appendChild(celda);
    cuerpoTablaAnuncios.appendChild(fila);
    dialogoVerAnuncios.showModal();
    return;
  }

  for (const anuncio of filas) {
    const filaPrincipal = document.createElement("tr");
    filaPrincipal.className = "fila-anuncio";

    const celdaToggle = document.createElement("td");
    const botonToggle = document.createElement("button");
    botonToggle.type = "button";
    botonToggle.className = "boton-expandir";
    botonToggle.textContent = "▶";
    botonToggle.setAttribute("aria-label", "Ver título y mensaje completos");
    celdaToggle.appendChild(botonToggle);
    filaPrincipal.appendChild(celdaToggle);

    const columnas = [
      [anuncio.nro, "number"],
      [anuncio.semana, "text"],
      [anuncio.tipo, "text"],
      [anuncio.fecha, "date"],
      [anuncio.hora, "time"],
    ];

    for (const [valor, tipo] of columnas) {
      const celda = document.createElement("td");
      celda.appendChild(crearCeldaEditable(valor, tipo));
      filaPrincipal.appendChild(celda);
    }

    const filaDetalle = crearFilaDetalle(anuncio);
    botonToggle.addEventListener("click", () => {
      const seVaAMostrar = filaDetalle.classList.contains("oculto");
      filaDetalle.classList.toggle("oculto");
      botonToggle.textContent = seVaAMostrar ? "▼" : "▶";
    });

    cuerpoTablaAnuncios.append(filaPrincipal, filaDetalle);
  }

  dialogoVerAnuncios.showModal();
}

botonVerAnuncios.addEventListener("click", abrirVistaAnuncios);
botonCerrarVerAnuncios.addEventListener("click", () => dialogoVerAnuncios.close());

// --- Cursos activos ---

const tarjetaCursos = document.getElementById("tarjeta-cursos");
const cargandoCursos = document.getElementById("cargando-cursos");
const listaCursos = document.getElementById("lista-cursos");

let intervaloConsultaCursos = null;

async function iniciarObtenerCursos() {
  botonObtenerCursos.disabled = true;
  estadoCursosEl.textContent = "Buscando...";
  tarjetaCursos.classList.remove("oculto");
  cargandoCursos.classList.remove("oculto");
  listaCursos.innerHTML = "";

  const respuesta = await fetch("/api/cursos/obtener", { method: "POST" });
  if (!respuesta.ok) {
    const datos = await respuesta.json();
    alert(datos.error || "No se pudo iniciar la búsqueda de cursos.");
    botonObtenerCursos.disabled = false;
    cargandoCursos.classList.add("oculto");
    return;
  }

  intervaloConsultaCursos = setInterval(consultarEstadoCursos, 1000);
}

async function consultarEstadoCursos() {
  const respuesta = await fetch("/api/cursos/estado");
  const estado = await respuesta.json();

  if (estado.fase !== "terminado") {
    return;
  }

  // Se llega aquí también al cargar la página, si ya había una lista de
  // cursos guardada de una búsqueda anterior (ver _restaurar_cursos_guardados
  // en servidor.py): hay que mostrar la tarjeta aunque no se haya hecho
  // clic en "Obtener" en esta sesión del navegador.
  tarjetaCursos.classList.remove("oculto");

  clearInterval(intervaloConsultaCursos);
  cargandoCursos.classList.add("oculto");
  botonObtenerCursos.disabled = false;

  if (estado.resultado !== "ok") {
    estadoCursosEl.textContent = "No se pudo obtener";
    listaCursos.innerHTML = "";
    const item = document.createElement("li");
    item.className = "mensaje-cursos";
    item.textContent = "Ocurrió un problema. Revisa 'Ver detalles técnicos' en la sección de login.";
    listaCursos.appendChild(item);
    return;
  }

  cursosObtenidos = estado.cursos;
  actualizarBloqueoPlantilla();

  estadoCursosEl.textContent = estado.cursos.length + " curso(s) encontrado(s)";

  listaCursos.innerHTML = "";
  if (estado.cursos.length === 0) {
    const item = document.createElement("li");
    item.className = "mensaje-cursos";
    item.textContent = "No se encontraron cursos activos.";
    listaCursos.appendChild(item);
    return;
  }

  for (const curso of estado.cursos) {
    const item = document.createElement("li");

    const codigo = document.createElement("span");
    codigo.className = "codigo-curso";
    codigo.textContent = curso.codigo;

    const nombre = document.createElement("span");
    nombre.className = "nombre-curso";
    nombre.textContent = curso.nombre;

    item.appendChild(codigo);
    item.appendChild(nombre);
    listaCursos.appendChild(item);
  }
}

botonObtenerCursos.addEventListener("click", iniciarObtenerCursos);
