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
const cargando = document.getElementById("cargando");
const textoCargando = document.getElementById("texto-cargando");
const itemPlantilla = document.getElementById("item-plantilla");
const estadoPlantilla = document.getElementById("estado-plantilla");
const botonGenerarPlantilla = document.getElementById("boton-generar-plantilla");
const botonVerAnuncios = document.getElementById("boton-ver-anuncios");
const itemSesionesDictado = document.getElementById("item-sesiones-dictado");
const estadoSesionesDictado = document.getElementById("estado-sesiones-dictado");
const botonGenerarSesionesDictado = document.getElementById("boton-generar-sesiones-dictado");
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

// Nombre real del docente, detectado en el login de Blackboard (ver
// login.py). Se usa, por ejemplo, para firmar los mensajes de los anuncios
// semanales en vez de tener un nombre fijo.
let nombreDocenteActual = null;

function actualizarIdentidadDocente(estado, sesionActiva) {
  if (sesionActiva && estado.nombre_docente) {
    nombreDocenteEl.textContent = estado.nombre_docente;
    nombreDocenteActual = estado.nombre_docente;
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

// Fechas de inicio/fin configuradas por curso (botón "Configurar fechas" /
// "Editar fechas" en cada tarjeta de "Cursos activos"). "Generar Anuncios
// Semanales" y "Generar Sesiones Dictado" ya no piden estas fechas en sus
// propios formularios: las leen de aquí, y además permanecen bloqueadas
// hasta que al menos un curso tenga sus fechas configuradas.
let cursosFechas = {};

async function cargarCursosFechas() {
  const respuesta = await fetch("/api/cursos/fechas");
  cursosFechas = await respuesta.json();
}

function hayCursoConFechas() {
  return cursosObtenidos.some((curso) => cursosFechas[curso.codigo]);
}

// Horarios de dictado configurados por curso (botón "Agregar horario de
// dictado" / "Editar horario de dictado" en cada tarjeta de "Cursos
// activos"), para saber si mostrar ese botón como "Agregar" o "Editar".
let cursosSesiones = {};

async function cargarCursosSesiones() {
  const respuesta = await fetch("/api/sesiones-dictado");
  cursosSesiones = await respuesta.json();
}

function actualizarBloqueoHerramientas(sesionActiva) {
  botonObtenerCursos.disabled = !sesionActiva;
  itemCursos.classList.toggle("bloqueada", !sesionActiva);
  if (!sesionActiva) {
    estadoCursosEl.textContent = "Inicia sesión primero";
  } else if (estadoCursosEl.textContent === "Inicia sesión primero") {
    estadoCursosEl.textContent = "Disponible";
  }

  actualizarBloqueoPlantilla();
  actualizarBloqueoSesionesDictado();
}

function actualizarBloqueoPlantilla() {
  const hayCursos = cursosObtenidos.length > 0;
  const disponible = hayCursos && hayCursoConFechas();
  botonGenerarPlantilla.disabled = !disponible;
  itemPlantilla.classList.toggle("bloqueada", !disponible);
  estadoPlantilla.textContent = !hayCursos
    ? "Obtén tus cursos primero"
    : !disponible
      ? "Configura las fechas de un curso primero"
      : "Disponible";
}

function actualizarBloqueoSesionesDictado() {
  const hayCursos = cursosObtenidos.length > 0;
  const disponible = hayCursos && hayCursoConFechas();
  botonGenerarSesionesDictado.disabled = !disponible;
  itemSesionesDictado.classList.toggle("bloqueada", !disponible);
  estadoSesionesDictado.textContent = !hayCursos
    ? "Obtén tus cursos primero"
    : !disponible
      ? "Configura las fechas de un curso primero"
      : "Disponible";
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
const campoDiaInicio = document.getElementById("campo-dia-inicio");
const campoHoraInicio = document.getElementById("campo-hora-inicio");
const campoDiaFin = document.getElementById("campo-dia-fin");
const campoHoraFin = document.getElementById("campo-hora-fin");
const mensajeAsistenteAnuncios = document.getElementById("mensaje-asistente-anuncios");
const botonGuardarAnuncios = document.getElementById("boton-guardar-anuncios-semanales");
const botonCancelarAnuncios = document.getElementById("boton-cancelar-anuncios-semanales");
const campoConfirmarFechaPasada = document.getElementById("campo-confirmar-fecha-pasada");
const casillaConfirmarFechaPasada = document.getElementById("casilla-confirmar-fecha-pasada");
const campoRegularizarFechaManual = document.getElementById("campo-regularizar-fecha-manual");
const casillaRegularizarFechaManual = document.getElementById("casilla-regularizar-fecha-manual");
const campoFechaRegularizacionManual = document.getElementById("campo-fecha-regularizacion-manual");
const campoFechaRegularizacion = document.getElementById("campo-fecha-regularizacion");
const casillaEliminarAnunciosExistentes = document.getElementById("casilla-eliminar-anuncios-existentes");
const dialogoGuardadoOk = document.getElementById("dialogo-guardado-ok");
const botonCerrarGuardadoOk = document.getElementById("boton-cerrar-guardado-ok");

const DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
const CAMPOS_REQUERIDOS_ANUNCIOS = [
  "curso_codigo",
  "curso_nombre",
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

// Las casillas de "regularizar" (desde el inicio real del curso, o desde
// una fecha manual) solo tienen sentido -y solo se muestran- cuando la
// fecha de inicio del curso elegido (ver cursosFechas, cargada desde
// "Cursos activos") ya pasó. Son mutuamente excluyentes: solo una puede
// estar marcada a la vez.
function actualizarVisibilidadCasillaFechaPasada() {
  const fechasCurso = cursosFechas[campoCurso.value];
  const fechaInicioCurso = fechasCurso ? fechasCurso.fecha_inicio_curso : "";
  const fechaPasada = Boolean(fechaInicioCurso) && fechaInicioCurso < fechaHoyISO();
  campoConfirmarFechaPasada.classList.toggle("oculto", !fechaPasada);
  campoRegularizarFechaManual.classList.toggle("oculto", !fechaPasada);
  if (!fechaPasada) {
    casillaConfirmarFechaPasada.checked = false;
    casillaRegularizarFechaManual.checked = false;
  }
  actualizarVisibilidadFechaRegularizacionManual();
}

function actualizarVisibilidadFechaRegularizacionManual() {
  campoFechaRegularizacionManual.classList.toggle("oculto", !casillaRegularizarFechaManual.checked);
  if (!casillaRegularizarFechaManual.checked) {
    campoFechaRegularizacion.value = "";
  }
}

casillaConfirmarFechaPasada.addEventListener("change", () => {
  if (casillaConfirmarFechaPasada.checked) {
    casillaRegularizarFechaManual.checked = false;
    actualizarVisibilidadFechaRegularizacionManual();
  }
});

casillaRegularizarFechaManual.addEventListener("change", () => {
  if (casillaRegularizarFechaManual.checked) {
    casillaConfirmarFechaPasada.checked = false;
  }
  actualizarVisibilidadFechaRegularizacionManual();
});

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

  campoDiaInicio.value = configuracion ? configuracion.dia_inicio_semana : campoDiaInicio.options[0].value;
  campoHoraInicio.value = configuracion ? configuracion.hora_inicio_semana : "";
  campoDiaFin.value = configuracion ? configuracion.dia_fin_semana : campoDiaFin.options[0].value;
  campoHoraFin.value = configuracion ? configuracion.hora_fin_semana : "";
  casillaConfirmarFechaPasada.checked = configuracion ? Boolean(configuracion.confirmar_fecha_pasada) : false;
  casillaRegularizarFechaManual.checked = configuracion ? Boolean(configuracion.regularizar_fecha_manual) : false;
  campoFechaRegularizacion.value = configuracion ? configuracion.fecha_regularizacion_manual || "" : "";
  casillaEliminarAnunciosExistentes.checked = configuracion ? Boolean(configuracion.eliminar_anuncios_existentes) : false;

  actualizarVisibilidadCasillaFechaPasada();

  if (configuracion) {
    configuracionAnunciosActual = configuracion;
    botonVerAnuncios.disabled = false;
  }
}

function abrirAsistenteAnuncios() {
  campoCurso.innerHTML = "";
  // Solo se listan los cursos que ya tienen fecha de inicio/fin configurada
  // desde "Cursos activos": este asistente ya no las pide.
  for (const curso of cursosObtenidos) {
    if (!cursosFechas[curso.codigo]) continue;
    const opcion = document.createElement("option");
    opcion.value = curso.codigo;
    opcion.textContent = curso.nombre;
    campoCurso.appendChild(opcion);
  }

  mensajeAsistenteAnuncios.textContent = "";
  botonVerAnuncios.disabled = true;
  precargarConfiguracionGuardada(campoCurso.value);
  actualizarVisibilidadCasillaFechaPasada();
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
    dia_inicio_semana: campoDiaInicio.value,
    hora_inicio_semana: campoHoraInicio.value,
    dia_fin_semana: campoDiaFin.value,
    hora_fin_semana: campoHoraFin.value,
    confirmar_fecha_pasada: casillaConfirmarFechaPasada.checked,
    regularizar_fecha_manual: casillaRegularizarFechaManual.checked,
    fecha_regularizacion_manual: campoFechaRegularizacion.value,
    eliminar_anuncios_existentes: casillaEliminarAnunciosExistentes.checked,
  };

  const faltaAlgo = CAMPOS_REQUERIDOS_ANUNCIOS.some((campo) => !datos[campo]);
  if (faltaAlgo) {
    mensajeAsistenteAnuncios.textContent = "Completa todos los campos antes de guardar.";
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

  if (datos.regularizar_fecha_manual && !datos.fecha_regularizacion_manual) {
    mensajeAsistenteAnuncios.textContent = "Selecciona la fecha desde la cual deseas regularizar.";
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
const botonGenerarEnBlackboard = document.getElementById("boton-generar-en-blackboard");

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

// Convierte el nombre tal como lo devuelve Blackboard (normalmente en
// MAYÚSCULAS) a formato Título, ej. "GIAN CARLO QUIROZ" -> "Gian Carlo Quiroz".
function formatearNombreDocente(nombre) {
  return nombre
    .toLowerCase()
    .split(" ")
    .filter(Boolean)
    .map((palabra) => palabra.charAt(0).toUpperCase() + palabra.slice(1))
    .join(" ");
}

// Nombre para firmar los anuncios, tomado del docente detectado en el login
// de Blackboard (ver nombreDocenteActual); nunca un nombre fijo.
function nombreFirmaDocente() {
  return nombreDocenteActual ? formatearNombreDocente(nombreDocenteActual) : "el/la Docente";
}

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
Profesor ${nombreFirmaDocente()}`;
}

function generarMensajeFin(indice) {
  const ordinal = ORDINALES_SEMANA[indice];

  return `Tema: Conclusiones de la ${ordinal} Semana

¡Felicitaciones por el trabajo realizado esta semana! 👏✨
Han continuado fortaleciendo sus conocimientos y desarrollando nuevas habilidades que les permitirán afrontar los siguientes temas con mayor seguridad. Cada ejercicio y actividad realizada representa un paso importante en su proceso de aprendizaje. 📖💪

Los animo a repasar lo trabajado durante la semana y a seguir practicando. La constancia es la clave para lograr excelentes resultados. ¡Nos vemos en la siguiente sesión con nuevos retos y aprendizajes! 🚀

Saludos,
Profesor ${nombreFirmaDocente()}`;
}

// Título corto del anuncio, según el formato pedido.
function tituloAnuncio(tipo, numeroSemana) {
  return tipo === "Inicio" ? `INICIO SEMANA ${numeroSemana} 🚀🌐` : `CIERRE DE SEMANA ${numeroSemana} ✅🎉`;
}

// Mensaje de la base (20 para inicio, 20 para fin), usado en orden según el
// número real de semana del curso; si el curso tiene más de 20 semanas, se
// vuelve a empezar desde la primera de la base. Se genera al vuelo (no se
// precalcula) porque incluye el nombre del docente, ya detectado en ese
// momento gracias al login previo.
function mensajeDeLaBase(tipo, numeroSemana) {
  const indice = (numeroSemana - 1) % ORDINALES_SEMANA.length;
  return tipo === "Inicio" ? generarMensajeInicio(indice) : generarMensajeFin(indice);
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
// mostrar desde el próximo anuncio disponible (>= hoy).
//
// Esto se puede cambiar con una de dos casillas, mutuamente excluyentes:
// - "confirmar_fecha_pasada": no se omite nada, se muestran todas desde la
//   fecha real de inicio del curso.
// - "regularizar_fecha_manual" + "fecha_regularizacion_manual": en vez de
//   "hoy", se usa esa fecha elegida a mano como punto de corte.
function generarFilasAnuncios(configuracion) {
  const indiceInicio = DIAS_SEMANA.findIndex((dia) => dia.toLowerCase() === configuracion.dia_inicio_semana);
  const indiceFin = DIAS_SEMANA.findIndex((dia) => dia.toLowerCase() === configuracion.dia_fin_semana);
  const desfaseFin = indiceFin - indiceInicio;

  // Primera fecha en la que cae el día de "inicio de semana", a partir del
  // inicio real del curso (puede ser esa misma fecha, o unos días después).
  const desfaseHastaPrimerInicio = (indiceInicio - indiceDiaSemana(configuracion.fecha_inicio_curso) + 7) % 7;
  let fechaInicioSemana = sumarDias(configuracion.fecha_inicio_curso, desfaseHastaPrimerInicio);

  // Punto de corte: null significa "no omitir nada".
  const fechaCorte = configuracion.confirmar_fecha_pasada
    ? null
    : configuracion.regularizar_fecha_manual && configuracion.fecha_regularizacion_manual
      ? configuracion.fecha_regularizacion_manual
      : fechaHoyISO();

  const filas = [];
  let numeroSemana = 1;
  let nro = 1;

  while (fechaInicioSemana <= configuracion.fecha_fin_curso) {
    const fechaFinSemana = sumarDias(fechaInicioSemana, desfaseFin);

    if (fechaCorte === null || fechaInicioSemana >= fechaCorte) {
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

    if (fechaCorte === null || fechaFinSemana >= fechaCorte) {
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

  // La fecha de inicio/fin del curso ya no vive en esta configuración: se
  // toma de "Cursos activos" (cursosFechas), la fuente única para ambas
  // herramientas.
  const fechasCurso = cursosFechas[configuracionAnunciosActual.curso_codigo];
  if (!fechasCurso) {
    return;
  }

  const filas = generarFilasAnuncios({ ...configuracionAnunciosActual, ...fechasCurso });

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

// Lee la grilla de anuncios directamente del DOM (no de configuracionAnunciosActual),
// para respetar cualquier edición manual que haya hecho el docente. Cada fila
// principal (Nro/Semana/Tipo/Fecha/Hora) va seguida de su fila de detalle
// oculta (Título/Mensaje); se recorren de a pares. Devuelve también las
// celdas de título/mensaje, para poder sobrescribirlas al importar un CSV.
function leerFilasDesdeTabla() {
  const filasTabla = Array.from(cuerpoTablaAnuncios.children);
  const filas = [];

  for (let indice = 0; indice < filasTabla.length; indice += 2) {
    const filaPrincipal = filasTabla[indice];
    const filaDetalle = filasTabla[indice + 1];
    if (!filaPrincipal || !filaDetalle) continue;

    const inputsPrincipales = filaPrincipal.querySelectorAll("input");
    const camposDetalle = filaDetalle.querySelectorAll(".celda-editable");

    filas.push({
      semana: inputsPrincipales[1].value,
      tipo: inputsPrincipales[2].value,
      fecha: inputsPrincipales[3].value,
      hora: inputsPrincipales[4].value,
      titulo: camposDetalle[0].value,
      mensaje: camposDetalle[1].value,
      campoTitulo: camposDetalle[0],
      campoMensaje: camposDetalle[1],
    });
  }

  return filas;
}

// --- Exportar / Importar anuncios (CSV) ---
// Exporta solo semana, tipo, título y mensaje (lo único que un docente
// necesita redactar aparte); fecha y hora quedan definidas por el asistente
// y no se tocan al importar. Al importar, cada fila del CSV se encaja en la
// grilla actual por semana + tipo, sin depender del orden de las filas.

const botonExportarAnuncios = document.getElementById("boton-exportar-anuncios");
const botonImportarAnuncios = document.getElementById("boton-importar-anuncios");
const campoImportarAnuncios = document.getElementById("campo-importar-anuncios");

// Encierra el valor entre comillas solo si lo necesita (contiene coma,
// comillas o salto de línea), duplicando las comillas internas, siguiendo
// el formato CSV estándar (RFC 4180) para que Excel lo abra sin problemas.
function csvEscape(valor) {
  const texto = String(valor ?? "");
  if (/[",\r\n]/.test(texto)) {
    return '"' + texto.replace(/"/g, '""') + '"';
  }
  return texto;
}

// Parser CSV manual (sin librerías): entiende comillas, comas y saltos de
// línea dentro de campos entre comillas, que es justo lo que necesita el
// mensaje de un anuncio (varios párrafos).
function parsearCSV(texto) {
  const filas = [];
  let fila = [];
  let campo = "";
  let dentroDeComillas = false;
  let indice = 0;

  while (indice < texto.length) {
    const caracter = texto[indice];

    if (dentroDeComillas) {
      if (caracter === '"') {
        if (texto[indice + 1] === '"') {
          campo += '"';
          indice += 2;
          continue;
        }
        dentroDeComillas = false;
        indice += 1;
        continue;
      }
      campo += caracter;
      indice += 1;
      continue;
    }

    if (caracter === '"') {
      dentroDeComillas = true;
      indice += 1;
    } else if (caracter === ",") {
      fila.push(campo);
      campo = "";
      indice += 1;
    } else if (caracter === "\r") {
      indice += 1;
    } else if (caracter === "\n") {
      fila.push(campo);
      filas.push(fila);
      fila = [];
      campo = "";
      indice += 1;
    } else {
      campo += caracter;
      indice += 1;
    }
  }

  if (campo !== "" || fila.length > 0) {
    fila.push(campo);
    filas.push(fila);
  }

  return filas;
}

// Convierte las filas crudas del CSV (con su fila de encabezado) en objetos
// {semana, tipo, titulo, mensaje}, buscando las columnas por nombre en vez
// de asumir un orden fijo, por si el docente reordena columnas en Excel.
function filasCSVaObjetos(filasCrudas) {
  if (filasCrudas.length === 0) {
    return [];
  }

  const encabezado = filasCrudas[0].map((valor) => valor.trim().toLowerCase());
  const indiceSemana = encabezado.indexOf("semana");
  const indiceTipo = encabezado.indexOf("tipo");
  const indiceTitulo = encabezado.indexOf("titulo");
  const indiceMensaje = encabezado.indexOf("mensaje");

  const objetos = [];
  for (let i = 1; i < filasCrudas.length; i++) {
    const fila = filasCrudas[i];
    if (fila.length === 1 && fila[0].trim() === "") continue; // línea vacía al final

    objetos.push({
      semana: indiceSemana >= 0 ? fila[indiceSemana] || "" : "",
      tipo: indiceTipo >= 0 ? fila[indiceTipo] || "" : "",
      titulo: indiceTitulo >= 0 ? fila[indiceTitulo] || "" : "",
      mensaje: indiceMensaje >= 0 ? fila[indiceMensaje] || "" : "",
    });
  }
  return objetos;
}

function descargarArchivo(contenido, nombreArchivo, tipoMime) {
  const blob = new Blob([contenido], { type: tipoMime });
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombreArchivo;
  document.body.appendChild(enlace);
  enlace.click();
  document.body.removeChild(enlace);
  URL.revokeObjectURL(url);
}

function exportarAnuncios() {
  const filas = leerFilasDesdeTabla();
  if (filas.length === 0) {
    mostrarResultadoBlackboard("Nada que exportar", "Primero genera la vista de anuncios.");
    return;
  }

  const lineas = [["semana", "tipo", "titulo", "mensaje"].map(csvEscape).join(",")];
  for (const fila of filas) {
    lineas.push([fila.semana, fila.tipo, fila.titulo, fila.mensaje].map(csvEscape).join(","));
  }

  // El BOM al inicio hace que Excel detecte UTF-8 automáticamente; sin él,
  // las tildes y emojis del mensaje se ven mal al abrir el CSV en Excel.
  const contenido = "﻿" + lineas.join("\r\n");
  const codigoCurso = configuracionAnunciosActual ? configuracionAnunciosActual.curso_codigo : "curso";
  descargarArchivo(contenido, `anuncios_${codigoCurso}.csv`, "text/csv;charset=utf-8");
}

function normalizarClave(valor) {
  return String(valor || "").trim().toLowerCase();
}

function importarAnunciosDesdeCSV(texto) {
  const filasTabla = leerFilasDesdeTabla();
  if (filasTabla.length === 0) {
    mostrarResultadoBlackboard("Nada que importar", "Primero genera la vista de anuncios.");
    return;
  }

  const filasCSV = filasCSVaObjetos(parsearCSV(texto));
  if (filasCSV.length === 0) {
    mostrarResultadoBlackboard("Archivo vacío", "El archivo no tiene filas para importar.");
    return;
  }

  let aplicadas = 0;
  const sinCoincidencia = [];

  for (const filaCSV of filasCSV) {
    const clave = `${normalizarClave(filaCSV.semana)}|${normalizarClave(filaCSV.tipo)}`;
    const filaEncontrada = filasTabla.find(
      (fila) => `${normalizarClave(fila.semana)}|${normalizarClave(fila.tipo)}` === clave
    );
    if (!filaEncontrada) {
      sinCoincidencia.push(`${filaCSV.semana} - ${filaCSV.tipo}`);
      continue;
    }
    filaEncontrada.campoTitulo.value = filaCSV.titulo;
    filaEncontrada.campoMensaje.value = filaCSV.mensaje;
    aplicadas += 1;
  }

  let mensaje = `Se completaron ${aplicadas} de ${filasCSV.length} fila(s) del archivo.`;
  if (sinCoincidencia.length > 0) {
    mensaje += ` Sin coincidencia de semana/tipo en la grilla actual: ${sinCoincidencia.join(", ")}.`;
  }
  mostrarResultadoBlackboard("Importación completada", mensaje);
}

botonExportarAnuncios.addEventListener("click", exportarAnuncios);
botonImportarAnuncios.addEventListener("click", () => campoImportarAnuncios.click());
campoImportarAnuncios.addEventListener("change", async () => {
  const archivo = campoImportarAnuncios.files[0];
  campoImportarAnuncios.value = ""; // permite elegir el mismo archivo otra vez más adelante
  if (!archivo) {
    return;
  }
  const texto = await archivo.text();
  importarAnunciosDesdeCSV(texto);
});

// --- Generar en Blackboard ---
// Toma exactamente lo que se ve en la grilla (con cualquier edición manual
// del docente) y crea cada fila como un anuncio real en Blackboard, usando
// el panel "Crear anuncio" del curso. Los avisos y la confirmación usan
// diálogos propios (mismo estilo que "Guardado correctamente"), no los
// popups nativos del navegador (alert/confirm).

const dialogoConfirmarBlackboard = document.getElementById("dialogo-confirmar-blackboard");
const mensajeConfirmarBlackboard = document.getElementById("mensaje-confirmar-blackboard");
const botonConfirmarGenerarBlackboard = document.getElementById("boton-confirmar-generar-blackboard");
const botonCancelarGenerarBlackboard = document.getElementById("boton-cancelar-generar-blackboard");

const dialogoResultadoBlackboard = document.getElementById("dialogo-resultado-blackboard");
const tituloResultadoBlackboard = document.getElementById("titulo-resultado-blackboard");
const mensajeResultadoBlackboard = document.getElementById("mensaje-resultado-blackboard");
const botonCerrarResultadoBlackboard = document.getElementById("boton-cerrar-resultado-blackboard");

function mostrarResultadoBlackboard(titulo, mensaje) {
  tituloResultadoBlackboard.textContent = titulo;
  mensajeResultadoBlackboard.textContent = mensaje;
  dialogoResultadoBlackboard.showModal();
}

botonCerrarResultadoBlackboard.addEventListener("click", () => dialogoResultadoBlackboard.close());

// Envuelve el diálogo de confirmación en una promesa, para poder usarlo con
// await igual que se usaba confirm() antes.
function confirmarGenerarEnBlackboard(mensaje) {
  return new Promise((resolve) => {
    mensajeConfirmarBlackboard.textContent = mensaje;

    function aceptar() {
      limpiar();
      dialogoConfirmarBlackboard.close();
      resolve(true);
    }
    function cancelar() {
      limpiar();
      dialogoConfirmarBlackboard.close();
      resolve(false);
    }
    function limpiar() {
      botonConfirmarGenerarBlackboard.removeEventListener("click", aceptar);
      botonCancelarGenerarBlackboard.removeEventListener("click", cancelar);
    }

    botonConfirmarGenerarBlackboard.addEventListener("click", aceptar);
    botonCancelarGenerarBlackboard.addEventListener("click", cancelar);
    dialogoConfirmarBlackboard.showModal();
  });
}

async function generarEnBlackboard() {
  const filasTabla = leerFilasDesdeTabla();
  if (filasTabla.length === 0) {
    mostrarResultadoBlackboard("Falta un paso", "Primero genera la vista de anuncios.");
    return;
  }

  const codigoCurso = configuracionAnunciosActual && configuracionAnunciosActual.curso_codigo;
  const cursoInfo = cursosObtenidos.find((curso) => curso.codigo === codigoCurso);
  if (!cursoInfo || !cursoInfo.id) {
    mostrarResultadoBlackboard(
      "No se pudo identificar el curso",
      'Vuelve a hacer clic en "Obtener Cursos Activos" para actualizar la lista de cursos, y luego intenta de nuevo.'
    );
    return;
  }

  const anuncios = filasTabla.map(({ tipo, titulo, mensaje, fecha, hora }) => ({ tipo, titulo, mensaje, fecha, hora }));

  const confirmado = await confirmarGenerarEnBlackboard(
    `Esto creará ${anuncios.length} anuncio(s) reales en Blackboard, en el curso "${cursoInfo.nombre}". ¿Deseas continuar?`
  );
  if (!confirmado) {
    return;
  }

  botonGenerarEnBlackboard.disabled = true;
  const textoOriginal = botonGenerarEnBlackboard.textContent;
  botonGenerarEnBlackboard.textContent = "Generando...";

  try {
    const respuesta = await fetch("/api/anuncios-semanales/generar-en-blackboard", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_curso: cursoInfo.id, anuncios }),
    });
    const resultado = await respuesta.json();

    if (resultado.estado === "error") {
      mostrarResultadoBlackboard(
        "No se pudo generar",
        resultado.error || "No se pudo generar los anuncios en Blackboard."
      );
      return;
    }

    let mensajeResultado = `Se publicaron ${resultado.publicados} de ${anuncios.length} anuncio(s) en Blackboard.`;
    if (resultado.fallidos && resultado.fallidos.length > 0) {
      mensajeResultado += ` No se pudieron publicar: ${resultado.fallidos.join(", ")}.`;
    }
    mostrarResultadoBlackboard(resultado.fallidos && resultado.fallidos.length > 0 ? "Generado con avisos" : "Listo", mensajeResultado);
  } finally {
    botonGenerarEnBlackboard.disabled = false;
    botonGenerarEnBlackboard.textContent = textoOriginal;
  }
}

botonGenerarEnBlackboard.addEventListener("click", generarEnBlackboard);

// --- Cursos activos ---

const tarjetaCursos = document.getElementById("tarjeta-cursos");
const contadorCursos = document.getElementById("contador-cursos");
const fechaObtencionCursos = document.getElementById("fecha-obtencion-cursos");
const cargandoCursos = document.getElementById("cargando-cursos");
const listaCursos = document.getElementById("lista-cursos");

let intervaloConsultaCursos = null;

// Convierte el "obtenido_en" que devuelve el servidor (ISO local, sin zona
// horaria, ej. "2026-07-29T14:32:05") a un texto legible. Si no hay fecha
// (por ejemplo, una lista guardada por una versión anterior del programa),
// no se muestra nada.
function formatearFechaObtencionCursos(iso) {
  if (!iso) {
    return "";
  }
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) {
    return "";
  }
  const dia = String(fecha.getDate()).padStart(2, "0");
  const mes = String(fecha.getMonth() + 1).padStart(2, "0");
  const anio = fecha.getFullYear();
  const horas = String(fecha.getHours()).padStart(2, "0");
  const minutos = String(fecha.getMinutes()).padStart(2, "0");
  return `Obtenidos el ${dia}/${mes}/${anio} a las ${horas}:${minutos}`;
}

const dialogoConfirmarCursos = document.getElementById("dialogo-confirmar-cursos");
const botonConfirmarObtenerCursos = document.getElementById("boton-confirmar-obtener-cursos");
const botonCancelarObtenerCursos = document.getElementById("boton-cancelar-obtener-cursos");

// Envuelve el diálogo de confirmación en una promesa, igual que
// confirmarGenerarEnBlackboard, para poder usarlo con await.
function confirmarObtenerCursos() {
  return new Promise((resolve) => {
    function aceptar() {
      limpiar();
      dialogoConfirmarCursos.close();
      resolve(true);
    }
    function cancelar() {
      limpiar();
      dialogoConfirmarCursos.close();
      resolve(false);
    }
    function limpiar() {
      botonConfirmarObtenerCursos.removeEventListener("click", aceptar);
      botonCancelarObtenerCursos.removeEventListener("click", cancelar);
    }

    botonConfirmarObtenerCursos.addEventListener("click", aceptar);
    botonCancelarObtenerCursos.addEventListener("click", cancelar);
    dialogoConfirmarCursos.showModal();
  });
}

async function iniciarObtenerCursos() {
  const confirmado = await confirmarObtenerCursos();
  if (!confirmado) {
    return;
  }

  botonObtenerCursos.disabled = true;
  estadoCursosEl.textContent = "Buscando...";
  contadorCursos.textContent = "";
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
    contadorCursos.textContent = "";
    fechaObtencionCursos.textContent = "";
    listaCursos.innerHTML = "";
    const item = document.createElement("li");
    item.className = "mensaje-cursos";
    item.textContent = "Ocurrió un problema. Revisa 'Ver detalles técnicos' en la sección de login.";
    listaCursos.appendChild(item);
    return;
  }

  cursosObtenidos = estado.cursos;
  await cargarCursosFechas();
  await cargarCursosSesiones();
  actualizarBloqueoPlantilla();
  actualizarBloqueoSesionesDictado();

  estadoCursosEl.textContent = estado.cursos.length + " curso(s) encontrado(s)";
  contadorCursos.textContent = estado.cursos.length + " curso(s)";
  fechaObtencionCursos.textContent = formatearFechaObtencionCursos(estado.obtenido_en);

  listaCursos.innerHTML = "";
  if (estado.cursos.length === 0) {
    const item = document.createElement("li");
    item.className = "mensaje-cursos";
    item.textContent = "No se encontraron cursos activos.";
    listaCursos.appendChild(item);
    return;
  }

  elementosTarjetasCursos = {};

  for (const curso of estado.cursos) {
    const item = document.createElement("li");

    const codigo = document.createElement("span");
    codigo.className = "codigo-curso";
    codigo.textContent = curso.codigo;

    const nombre = document.createElement("span");
    nombre.className = "nombre-curso";
    nombre.textContent = curso.nombre;

    const fechas = document.createElement("span");
    fechas.className = "fechas-curso";

    const botonFechas = document.createElement("button");
    botonFechas.type = "button";
    botonFechas.className = "boton-accion-curso";
    botonFechas.addEventListener("click", () => abrirModalFechasCurso(curso, fechas, botonFechas));

    const horario = document.createElement("span");
    horario.className = "horario-curso";

    const botonHorario = document.createElement("button");
    botonHorario.type = "button";
    botonHorario.className = "boton-accion-curso";
    botonHorario.addEventListener("click", () => abrirAsistenteSesiones(curso.codigo));

    elementosTarjetasCursos[curso.codigo] = { fechas, botonFechas, horario, botonHorario };

    actualizarFechasEnTarjeta(curso.codigo, fechas, botonFechas);
    actualizarHorarioEnTarjeta(curso.codigo, horario, botonHorario);

    item.append(codigo, nombre, fechas, botonFechas, horario, botonHorario);
    listaCursos.appendChild(item);
  }
}

botonObtenerCursos.addEventListener("click", iniciarObtenerCursos);

// --- Fechas de curso ---
// Cada tarjeta de curso tiene un botón para configurar su fecha de inicio y
// fin. Esa es ahora la única fuente de esas fechas: "Generar Anuncios
// Semanales" y "Generar Sesiones Dictado" las leen de aquí (cursosFechas) en
// vez de pedirlas otra vez en sus propios formularios.

const dialogoFechasCurso = document.getElementById("dialogo-fechas-curso");
const nombreCursoFechas = document.getElementById("nombre-curso-fechas");
const campoFechaInicioCurso = document.getElementById("campo-fecha-inicio-curso");
const campoFechaFinCurso = document.getElementById("campo-fecha-fin-curso");
const mensajeFechasCurso = document.getElementById("mensaje-fechas-curso");
const botonGuardarFechasCurso = document.getElementById("boton-guardar-fechas-curso");
const botonCancelarFechasCurso = document.getElementById("boton-cancelar-fechas-curso");

// Curso y elementos de su tarjeta que se están editando en el modal
// actualmente abierto, para poder actualizar esa misma tarjeta al guardar.
let cursoFechasActual = null;

// Elementos (fechas/horario, y sus botones) de cada tarjeta de curso
// actualmente renderizada, por código de curso. Se repuebla cada vez que se
// vuelve a dibujar la lista de "Cursos activos" (ver consultarEstadoCursos).
// Sirve para poder actualizar la tarjeta correcta después de guardar,
// incluso cuando el asistente se abrió desde el botón "Generar Sesiones
// Dictado" de la lista de Herramientas y no desde la propia tarjeta.
let elementosTarjetasCursos = {};

function formatearFechaCorta(iso) {
  if (!iso) {
    return "";
  }
  const [anio, mes, dia] = iso.split("-");
  return `${dia}/${mes}/${anio}`;
}

function actualizarFechasEnTarjeta(codigoCurso, fechasEl, botonEl) {
  const fechas = cursosFechas[codigoCurso];
  if (fechas) {
    fechasEl.textContent = `Del ${formatearFechaCorta(fechas.fecha_inicio_curso)} al ${formatearFechaCorta(fechas.fecha_fin_curso)}`;
    fechasEl.classList.remove("sin-configurar");
    botonEl.textContent = "Editar fechas";
  } else {
    fechasEl.textContent = "Sin fechas configuradas";
    fechasEl.classList.add("sin-configurar");
    botonEl.textContent = "Configurar fechas";
  }
}

function actualizarHorarioEnTarjeta(codigoCurso, horarioEl, botonEl) {
  const configurado = Boolean(cursosSesiones[codigoCurso]);
  const tieneFechas = Boolean(cursosFechas[codigoCurso]);

  horarioEl.textContent = configurado ? "Horario de dictado configurado" : "Sin horario de dictado";
  horarioEl.classList.toggle("sin-configurar", !configurado);

  botonEl.textContent = configurado ? "Editar horario de dictado" : "Agregar horario de dictado";
  botonEl.disabled = !tieneFechas;
  botonEl.title = tieneFechas ? "" : "Primero configura la fecha de inicio y fin de este curso.";
}

function abrirModalFechasCurso(curso, fechasEl, botonEl) {
  cursoFechasActual = { curso, fechasEl, botonEl };
  const fechas = cursosFechas[curso.codigo];
  nombreCursoFechas.textContent = curso.nombre;
  campoFechaInicioCurso.value = fechas ? fechas.fecha_inicio_curso : "";
  campoFechaFinCurso.value = fechas ? fechas.fecha_fin_curso : "";
  mensajeFechasCurso.textContent = "";
  dialogoFechasCurso.showModal();
}

async function guardarFechasCurso() {
  if (!cursoFechasActual) {
    return;
  }

  const datos = {
    curso_codigo: cursoFechasActual.curso.codigo,
    fecha_inicio_curso: campoFechaInicioCurso.value,
    fecha_fin_curso: campoFechaFinCurso.value,
  };

  if (!datos.fecha_inicio_curso || !datos.fecha_fin_curso) {
    mensajeFechasCurso.textContent = "Completa ambas fechas.";
    return;
  }

  if (datos.fecha_inicio_curso >= datos.fecha_fin_curso) {
    mensajeFechasCurso.textContent = "La fecha de inicio debe ser anterior a la fecha de fin.";
    return;
  }

  botonGuardarFechasCurso.disabled = true;
  const respuesta = await fetch("/api/cursos/fechas/guardar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(datos),
  });
  const resultado = await respuesta.json();
  botonGuardarFechasCurso.disabled = false;

  if (resultado.estado !== "ok") {
    mensajeFechasCurso.textContent = resultado.error || "No se pudo guardar la fecha del curso.";
    return;
  }

  cursosFechas[datos.curso_codigo] = {
    fecha_inicio_curso: datos.fecha_inicio_curso,
    fecha_fin_curso: datos.fecha_fin_curso,
  };
  actualizarFechasEnTarjeta(datos.curso_codigo, cursoFechasActual.fechasEl, cursoFechasActual.botonEl);
  // Configurar las fechas puede ser justo lo que faltaba para habilitar el
  // botón de horario de dictado de esta misma tarjeta.
  const elementos = elementosTarjetasCursos[datos.curso_codigo];
  if (elementos) {
    actualizarHorarioEnTarjeta(datos.curso_codigo, elementos.horario, elementos.botonHorario);
  }
  actualizarBloqueoPlantilla();
  actualizarBloqueoSesionesDictado();
  dialogoFechasCurso.close();
}

botonGuardarFechasCurso.addEventListener("click", guardarFechasCurso);
botonCancelarFechasCurso.addEventListener("click", () => dialogoFechasCurso.close());

// --- Generar Sesiones Dictado ---
// Mismo patrón que "Generar Anuncios Semanales": un asistente que guarda
// la configuración por curso, y un botón "Ver Sesiones" que solo se
// habilita después de guardar y que genera la grilla real, desde la fecha
// de inicio del curso hasta su fecha de fin.

const dialogoSesiones = document.getElementById("dialogo-sesiones-dictado");
const campoCursoSesiones = document.getElementById("campo-curso-sesiones");
const tablaHorarioSemanal = document.getElementById("tabla-horario-semanal");
const mensajeAsistenteSesiones = document.getElementById("mensaje-asistente-sesiones");
const botonGuardarSesiones = document.getElementById("boton-guardar-sesiones-dictado");
const botonVerSesiones = document.getElementById("boton-ver-sesiones-dictado");
const botonCancelarSesiones = document.getElementById("boton-cancelar-sesiones-dictado");

const dialogoGuardadoSesionesOk = document.getElementById("dialogo-guardado-sesiones-ok");
const botonCerrarGuardadoSesionesOk = document.getElementById("boton-cerrar-guardado-sesiones-ok");

const dialogoVerSesiones = document.getElementById("dialogo-ver-sesiones");
const cuerpoTablaSesiones = document.getElementById("cuerpo-tabla-sesiones");
const botonAbrirFeriados = document.getElementById("boton-abrir-feriados");
const botonAbrirFeriadosTool = document.getElementById("boton-abrir-feriados-tool");
const botonCerrarVerSesiones = document.getElementById("boton-cerrar-ver-sesiones");

const dialogoReprogramarSesion = document.getElementById("dialogo-reprogramar-sesion");
const nombreSesionReprogramar = document.getElementById("nombre-sesion-reprogramar");
const campoFechaReprogramada = document.getElementById("campo-fecha-reprogramada");
const campoHoraInicioReprogramada = document.getElementById("campo-hora-inicio-reprogramada");
const campoHoraFinReprogramada = document.getElementById("campo-hora-fin-reprogramada");
const campoDetalleReprogramada = document.getElementById("campo-detalle-reprogramada");
const mensajeReprogramarSesion = document.getElementById("mensaje-reprogramar-sesion");
const botonGuardarReprogramarSesion = document.getElementById("boton-guardar-reprogramar-sesion");
const botonCancelarReprogramarSesion = document.getElementById("boton-cancelar-reprogramar-sesion");

const dialogoDetalleSesion = document.getElementById("dialogo-detalle-sesion");
const nombreSesionDetalle = document.getElementById("nombre-sesion-detalle");
const detalleFechaOriginal = document.getElementById("detalle-fecha-original");
const detalleHoraOriginal = document.getElementById("detalle-hora-original");
const detalleMotivoCambioFila = document.getElementById("detalle-motivo-cambio-fila");
const detalleMotivoCambio = document.getElementById("detalle-motivo-cambio");
const botonCerrarDetalleSesion = document.getElementById("boton-cerrar-detalle-sesion");

const dialogoFeriados = document.getElementById("dialogo-feriados");
const listaFeriados = document.getElementById("lista-feriados");
const campoNuevoFeriado = document.getElementById("campo-nuevo-feriado");
const campoMotivoNuevoFeriado = document.getElementById("campo-motivo-nuevo-feriado");
const botonAgregarFeriado = document.getElementById("boton-agregar-feriado");
const mensajeFeriados = document.getElementById("mensaje-feriados");
const botonCerrarFeriados = document.getElementById("boton-cerrar-feriados");

// Configuración de sesiones ya guardada con éxito en el asistente; "Ver
// Sesiones" solo se habilita después de guardar.
let configuracionSesionesActual = null;

// Sesiones "base" (fecha/hora originales, sin reprogramaciones) del curso
// que se está viendo en "Ver Sesiones", calculadas al abrir el modal.
let filasBaseSesionesActuales = [];

// Reprogramaciones puntuales del curso que se está viendo, como
// {fecha_original: {fecha_nueva, hora_inicio, hora_fin, detalle}}.
let reprogramacionesCurso = {};

// Sesión (ya con la reprogramación aplicada) sobre la que se hizo clic en
// "Cambiar", mientras el modal de reprogramar está abierto.
let sesionReprogramarActual = null;

// Últimos feriados cargados, como lista de {fecha, motivo} ordenada
// ascendentemente por fecha (ver ordenarFeriados). El servidor los guarda
// como {"YYYY-MM-DD": "motivo"}; se convierten a lista aquí para poder
// recorrerlos y ordenarlos con facilidad en el panel.
let ultimosFeriadosCargados = [];

function ordenarFeriados(feriados) {
  return [...feriados].sort((a, b) => (a.fecha < b.fecha ? -1 : a.fecha > b.fecha ? 1 : 0));
}

function objetoFeriadosALista(objeto) {
  return ordenarFeriados(Object.entries(objeto).map(([fecha, motivo]) => ({ fecha, motivo })));
}

function construirTablaHorarioSemanal() {
  tablaHorarioSemanal.innerHTML = "";
  for (const dia of DIAS_SEMANA) {
    const fila = document.createElement("div");
    fila.className = "fila-horario-dia";
    fila.dataset.dia = dia.toLowerCase();

    const nombre = document.createElement("span");
    nombre.className = "nombre-dia";
    nombre.textContent = dia;

    const horaInicio = document.createElement("input");
    horaInicio.type = "time";
    horaInicio.className = "hora-inicio-dia";
    horaInicio.setAttribute("aria-label", `Hora de inicio, ${dia}`);

    const horaFin = document.createElement("input");
    horaFin.type = "time";
    horaFin.className = "hora-fin-dia";
    horaFin.setAttribute("aria-label", `Hora de fin, ${dia}`);

    fila.append(nombre, horaInicio, horaFin);
    tablaHorarioSemanal.appendChild(fila);
  }
}

construirTablaHorarioSemanal();

function leerHorarioSemanalFormulario() {
  const horarios = {};
  for (const fila of tablaHorarioSemanal.querySelectorAll(".fila-horario-dia")) {
    const dia = fila.dataset.dia;
    const horaInicio = fila.querySelector(".hora-inicio-dia").value;
    const horaFin = fila.querySelector(".hora-fin-dia").value;
    if (horaInicio && horaFin) {
      horarios[dia] = { hora_inicio: horaInicio, hora_fin: horaFin };
    }
  }
  return horarios;
}

function precargarHorarioSemanalFormulario(horarios) {
  for (const fila of tablaHorarioSemanal.querySelectorAll(".fila-horario-dia")) {
    const dia = fila.dataset.dia;
    const valor = horarios && horarios[dia];
    fila.querySelector(".hora-inicio-dia").value = valor ? valor.hora_inicio : "";
    fila.querySelector(".hora-fin-dia").value = valor ? valor.hora_fin : "";
  }
}

async function precargarConfiguracionSesiones(codigoCurso) {
  mensajeAsistenteSesiones.textContent = "";

  let configuracion = null;
  if (codigoCurso) {
    const respuesta = await fetch(`/api/sesiones-dictado/${encodeURIComponent(codigoCurso)}`);
    const datos = await respuesta.json();
    if (datos && datos.curso_codigo) {
      configuracion = datos;
    }
  }

  precargarHorarioSemanalFormulario(configuracion ? configuracion.horarios : null);

  if (configuracion) {
    configuracionSesionesActual = configuracion;
    botonVerSesiones.disabled = false;
  }
}

// 'codigoPreseleccionado' se usa cuando el asistente se abre desde el botón
// "Agregar/Editar horario de dictado" de una tarjeta de curso puntual (ver
// consultarEstadoCursos), para que ese curso ya salga elegido en el select
// en vez del primero de la lista.
function abrirAsistenteSesiones(codigoPreseleccionado) {
  campoCursoSesiones.innerHTML = "";
  // Solo se listan los cursos que ya tienen fecha de inicio/fin configurada
  // desde "Cursos activos": este asistente ya no las pide.
  for (const curso of cursosObtenidos) {
    if (!cursosFechas[curso.codigo]) continue;
    const opcion = document.createElement("option");
    opcion.value = curso.codigo;
    opcion.textContent = curso.nombre;
    campoCursoSesiones.appendChild(opcion);
  }

  if (typeof codigoPreseleccionado === "string" && cursosFechas[codigoPreseleccionado]) {
    campoCursoSesiones.value = codigoPreseleccionado;
  }

  mensajeAsistenteSesiones.textContent = "";
  botonVerSesiones.disabled = true;
  precargarConfiguracionSesiones(campoCursoSesiones.value);
  dialogoSesiones.showModal();
}

campoCursoSesiones.addEventListener("change", () => {
  botonVerSesiones.disabled = true;
  precargarConfiguracionSesiones(campoCursoSesiones.value);
});

botonGenerarSesionesDictado.addEventListener("click", () => abrirAsistenteSesiones());
botonCancelarSesiones.addEventListener("click", () => dialogoSesiones.close());

async function guardarSesionesDictado() {
  const cursoSeleccionado = cursosObtenidos.find((curso) => curso.codigo === campoCursoSesiones.value);
  const horarios = leerHorarioSemanalFormulario();

  const datos = {
    curso_codigo: campoCursoSesiones.value,
    curso_nombre: cursoSeleccionado ? cursoSeleccionado.nombre : "",
    horarios,
  };

  if (!datos.curso_codigo) {
    mensajeAsistenteSesiones.textContent = "Selecciona un curso.";
    return;
  }

  if (Object.keys(horarios).length === 0) {
    mensajeAsistenteSesiones.textContent = "Marca al menos un día de la semana con hora de inicio y fin.";
    return;
  }

  for (const [dia, valor] of Object.entries(horarios)) {
    if (valor.hora_fin <= valor.hora_inicio) {
      mensajeAsistenteSesiones.textContent = `La hora de fin del ${dia} debe ser posterior a la de inicio.`;
      return;
    }
  }

  botonGuardarSesiones.disabled = true;
  const respuesta = await fetch("/api/sesiones-dictado/guardar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(datos),
  });
  const resultado = await respuesta.json();
  botonGuardarSesiones.disabled = false;

  if (resultado.estado !== "ok") {
    mensajeAsistenteSesiones.textContent = resultado.error || "No se pudo guardar la configuración.";
    return;
  }

  mensajeAsistenteSesiones.textContent = "";
  configuracionSesionesActual = datos;
  botonVerSesiones.disabled = false;

  cursosSesiones[datos.curso_codigo] = datos;
  const elementos = elementosTarjetasCursos[datos.curso_codigo];
  if (elementos) {
    actualizarHorarioEnTarjeta(datos.curso_codigo, elementos.horario, elementos.botonHorario);
  }

  dialogoGuardadoSesionesOk.showModal();
}

botonGuardarSesiones.addEventListener("click", guardarSesionesDictado);
botonCerrarGuardadoSesionesOk.addEventListener("click", () => dialogoGuardadoSesionesOk.close());

// Reordena "Nombres Apellidos" -> "Apellidos Nombres" para nombres de 4
// palabras (el patrón peruano más común: 2 nombres + 2 apellidos). Si no
// calzan exactamente 4 palabras, se deja el nombre tal como llegó de
// Blackboard, para no adivinar de más.
function nombreDocenteParaSesion() {
  if (!nombreDocenteActual) {
    return "";
  }
  const palabras = nombreDocenteActual.trim().split(/\s+/);
  if (palabras.length === 4) {
    return `${palabras[2]} ${palabras[3]} ${palabras[0]} ${palabras[1]}`;
  }
  return nombreDocenteActual;
}

// Arma una fila "base" por cada sesión de dictado, desde fecha_inicio_curso
// hasta fecha_fin_curso, usando el horario semanal guardado. Son las fechas
// y horas originales, antes de aplicar cualquier reprogramación puntual.
function generarFilasSesiones(configuracion) {
  const filas = [];
  let fecha = configuracion.fecha_inicio_curso;

  while (fecha <= configuracion.fecha_fin_curso) {
    const dia = DIAS_SEMANA[indiceDiaSemana(fecha)].toLowerCase();
    const horario = configuracion.horarios[dia];

    if (horario) {
      filas.push({ fecha, horaInicio: horario.hora_inicio, horaFin: horario.hora_fin });
    }

    fecha = sumarDias(fecha, 1);
  }

  return filas;
}

// Aplica las reprogramaciones puntuales (por fecha original) a las filas
// base, reordena por la fecha/hora resultante y renombra cada sesión según
// su posición final: es lo que hace que, al reprogramar una sesión, toda la
// grilla se reordene y las SESIÓN 01/02/... queden actualizadas.
function aplicarReprogramaciones(filasBase, reprogramaciones) {
  const filas = filasBase.map((sesion) => {
    const cambio = reprogramaciones[sesion.fecha];
    return {
      fechaOriginal: sesion.fecha,
      horaInicioOriginal: sesion.horaInicio,
      horaFinOriginal: sesion.horaFin,
      fecha: cambio ? cambio.fecha_nueva : sesion.fecha,
      horaInicio: cambio ? cambio.hora_inicio : sesion.horaInicio,
      horaFin: cambio ? cambio.hora_fin : sesion.horaFin,
      detalleCambio: cambio ? cambio.detalle : "",
      modificado: Boolean(cambio),
    };
  });

  filas.sort((a, b) => {
    if (a.fecha !== b.fecha) return a.fecha < b.fecha ? -1 : 1;
    return a.horaInicio < b.horaInicio ? -1 : a.horaInicio > b.horaInicio ? 1 : 0;
  });

  const codigoCorto = configuracionSesionesActual.curso_nombre.split(" ")[0];
  const nombreSinCodigo = configuracionSesionesActual.curso_nombre.slice(codigoCorto.length + 1);
  const nombreDocenteSesion = nombreDocenteParaSesion();

  filas.forEach((sesion, indice) => {
    const numeroSesion = String(indice + 1).padStart(2, "0");
    // 'nombreCorto' es lo que se ve en la columna de la tabla; 'sesion' es
    // el nombre completo (con curso y docente), reservado para los modales
    // de "Cambiar" y "Detalle".
    sesion.nombreCorto = `SESIÓN ${numeroSesion}`;
    sesion.sesion = `SESIÓN ${numeroSesion} - ${nombreSinCodigo} (${codigoCorto}) - ${nombreDocenteSesion}`;
  });

  return filas;
}

function actualizarResaltadoFeriados() {
  const feriados = new Set(ultimosFeriadosCargados.map((feriado) => feriado.fecha));
  for (const fila of cuerpoTablaSesiones.querySelectorAll("tr[data-fecha]")) {
    fila.classList.toggle("fila-feriado", feriados.has(fila.dataset.fecha));
  }
}

// Dibuja la tabla de "Ver Sesiones" a partir de filasBaseSesionesActuales +
// reprogramacionesCurso (ya cargadas). Se usa tanto al abrir el modal como
// después de guardar una reprogramación, sin tener que volver a pedir nada
// al servidor salvo la reprogramación misma.
function renderizarTablaSesiones() {
  cuerpoTablaSesiones.innerHTML = "";

  const filas = aplicarReprogramaciones(filasBaseSesionesActuales, reprogramacionesCurso);

  if (filas.length === 0) {
    const fila = document.createElement("tr");
    const celda = document.createElement("td");
    celda.colSpan = 5;
    celda.textContent = "No hay sesiones desde el inicio hasta el fin del curso, con el horario configurado.";
    fila.appendChild(celda);
    cuerpoTablaSesiones.appendChild(fila);
    return;
  }

  for (const sesion of filas) {
    const fila = document.createElement("tr");
    fila.dataset.fecha = sesion.fecha;
    fila.classList.toggle("fila-modificada", sesion.modificado);

    const columnas = [sesion.nombreCorto, formatearFechaCorta(sesion.fecha), sesion.horaInicio, sesion.horaFin];
    for (const valor of columnas) {
      const celda = document.createElement("td");
      celda.textContent = valor;
      fila.appendChild(celda);
    }

    const celdaAcciones = document.createElement("td");
    celdaAcciones.className = "celda-acciones-sesion";

    const botonCambiar = document.createElement("button");
    botonCambiar.type = "button";
    botonCambiar.className = "boton-pequeno";
    botonCambiar.textContent = "Cambiar";
    botonCambiar.addEventListener("click", () => abrirModalReprogramarSesion(sesion));

    const botonDetalle = document.createElement("button");
    botonDetalle.type = "button";
    botonDetalle.className = "boton-pequeno";
    botonDetalle.textContent = "Detalle";
    botonDetalle.addEventListener("click", () => abrirModalDetalleSesion(sesion));

    celdaAcciones.append(botonCambiar, botonDetalle);
    fila.appendChild(celdaAcciones);

    cuerpoTablaSesiones.appendChild(fila);
  }

  actualizarResaltadoFeriados();
}

async function abrirVistaSesiones() {
  cuerpoTablaSesiones.innerHTML = "";

  if (!configuracionSesionesActual) {
    return;
  }

  // La fecha de inicio/fin del curso ya no vive en esta configuración: se
  // toma de "Cursos activos" (cursosFechas), la fuente única para ambas
  // herramientas.
  const fechasCurso = cursosFechas[configuracionSesionesActual.curso_codigo];
  if (!fechasCurso) {
    return;
  }

  const [respuestaFeriados, respuestaReprogramaciones] = await Promise.all([
    fetch("/api/feriados"),
    fetch(`/api/sesiones-dictado/${encodeURIComponent(configuracionSesionesActual.curso_codigo)}/reprogramaciones`),
  ]);
  const datosFeriados = await respuestaFeriados.json();
  ultimosFeriadosCargados = objetoFeriadosALista(datosFeriados.feriados || {});
  reprogramacionesCurso = await respuestaReprogramaciones.json();

  filasBaseSesionesActuales = generarFilasSesiones({ ...configuracionSesionesActual, ...fechasCurso });

  renderizarTablaSesiones();
  dialogoVerSesiones.showModal();
}

botonVerSesiones.addEventListener("click", abrirVistaSesiones);
botonCerrarVerSesiones.addEventListener("click", () => dialogoVerSesiones.close());

// --- Reprogramar / ver detalle de una sesión puntual ---

function abrirModalReprogramarSesion(sesion) {
  sesionReprogramarActual = sesion;
  nombreSesionReprogramar.textContent = sesion.sesion;
  campoFechaReprogramada.value = sesion.fecha;
  campoHoraInicioReprogramada.value = sesion.horaInicio;
  campoHoraFinReprogramada.value = sesion.horaFin;
  campoDetalleReprogramada.value = sesion.detalleCambio || "";
  mensajeReprogramarSesion.textContent = "";
  dialogoReprogramarSesion.showModal();
}

async function guardarReprogramacionSesion() {
  if (!sesionReprogramarActual || !configuracionSesionesActual) {
    return;
  }

  const datos = {
    curso_codigo: configuracionSesionesActual.curso_codigo,
    fecha_original: sesionReprogramarActual.fechaOriginal,
    fecha_nueva: campoFechaReprogramada.value,
    hora_inicio: campoHoraInicioReprogramada.value,
    hora_fin: campoHoraFinReprogramada.value,
    detalle: campoDetalleReprogramada.value.trim(),
  };

  if (!datos.fecha_nueva || !datos.hora_inicio || !datos.hora_fin) {
    mensajeReprogramarSesion.textContent = "Completa la fecha y las horas.";
    return;
  }

  if (!datos.detalle) {
    mensajeReprogramarSesion.textContent = "Indica el detalle (motivo) del cambio.";
    return;
  }

  if (datos.hora_fin <= datos.hora_inicio) {
    mensajeReprogramarSesion.textContent = "La hora de fin debe ser posterior a la de inicio.";
    return;
  }

  botonGuardarReprogramarSesion.disabled = true;
  const respuesta = await fetch("/api/sesiones-dictado/reprogramar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(datos),
  });
  const resultado = await respuesta.json();
  botonGuardarReprogramarSesion.disabled = false;

  if (resultado.estado !== "ok") {
    mensajeReprogramarSesion.textContent = resultado.error || "No se pudo guardar la reprogramación.";
    return;
  }

  reprogramacionesCurso = resultado.reprogramaciones;
  dialogoReprogramarSesion.close();
  renderizarTablaSesiones();
}

botonGuardarReprogramarSesion.addEventListener("click", guardarReprogramacionSesion);
botonCancelarReprogramarSesion.addEventListener("click", () => dialogoReprogramarSesion.close());

function abrirModalDetalleSesion(sesion) {
  nombreSesionDetalle.textContent = sesion.sesion;
  detalleFechaOriginal.textContent = formatearFechaCorta(sesion.fechaOriginal);
  detalleHoraOriginal.textContent = `${sesion.horaInicioOriginal} - ${sesion.horaFinOriginal}`;
  detalleMotivoCambioFila.classList.toggle("oculto", !sesion.modificado);
  detalleMotivoCambio.textContent = sesion.detalleCambio || "";
  dialogoDetalleSesion.showModal();
}

botonCerrarDetalleSesion.addEventListener("click", () => dialogoDetalleSesion.close());

// --- Feriados ---
// Lista editable (agregar/quitar) usada para marcar en rojo las sesiones
// de dictado que caen en un día no laborable. Cada cambio se guarda de
// inmediato (no hay un botón "Guardar" aparte para esto).

function renderizarListaFeriados(feriados) {
  listaFeriados.innerHTML = "";
  const ordenados = ordenarFeriados(feriados);

  if (ordenados.length === 0) {
    const item = document.createElement("li");
    item.textContent = "No hay feriados guardados.";
    listaFeriados.appendChild(item);
    return;
  }

  for (const feriado of ordenados) {
    const item = document.createElement("li");

    const info = document.createElement("span");
    info.className = "info-feriado";

    const fecha = document.createElement("span");
    fecha.className = "fecha-feriado";
    fecha.textContent = formatearFechaCorta(feriado.fecha);

    const motivo = document.createElement("span");
    motivo.className = "motivo-feriado";
    motivo.textContent = feriado.motivo || "Sin motivo indicado";

    info.append(fecha, motivo);

    const botonQuitar = document.createElement("button");
    botonQuitar.type = "button";
    botonQuitar.className = "boton-quitar-feriado";
    botonQuitar.textContent = "Quitar";
    botonQuitar.addEventListener("click", () => quitarFeriado(feriado.fecha));

    item.append(info, botonQuitar);
    listaFeriados.appendChild(item);
  }
}

async function guardarListaFeriados(feriados) {
  const objeto = {};
  for (const feriado of feriados) {
    objeto[feriado.fecha] = feriado.motivo || "";
  }

  const respuesta = await fetch("/api/feriados", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ feriados: objeto }),
  });
  const resultado = await respuesta.json();
  ultimosFeriadosCargados = objetoFeriadosALista(resultado.feriados || {});
  renderizarListaFeriados(ultimosFeriadosCargados);
}

function quitarFeriado(fecha) {
  guardarListaFeriados(ultimosFeriadosCargados.filter((feriado) => feriado.fecha !== fecha));
}

function agregarFeriado() {
  const fecha = campoNuevoFeriado.value;
  const motivo = campoMotivoNuevoFeriado.value.trim();
  mensajeFeriados.textContent = "";

  if (!fecha || !motivo) {
    mensajeFeriados.textContent = "Completa la fecha y el motivo antes de agregar.";
    return;
  }

  // Si la fecha ya estaba en la lista, esto reemplaza su motivo en vez de
  // duplicarla.
  const sinEsaFecha = ultimosFeriadosCargados.filter((feriado) => feriado.fecha !== fecha);
  guardarListaFeriados([...sinEsaFecha, { fecha, motivo }]);

  campoNuevoFeriado.value = "";
  campoMotivoNuevoFeriado.value = "";
}

async function abrirFeriados() {
  const respuesta = await fetch("/api/feriados");
  const datos = await respuesta.json();
  ultimosFeriadosCargados = objetoFeriadosALista(datos.feriados || {});
  mensajeFeriados.textContent = "";
  renderizarListaFeriados(ultimosFeriadosCargados);
  dialogoFeriados.showModal();
}

botonAbrirFeriados.addEventListener("click", abrirFeriados);
// Mismo modal, accesible también directo desde la lista de Herramientas,
// sin tener que pasar por "Generar Sesiones Dictado" > "Ver Sesiones".
botonAbrirFeriadosTool.addEventListener("click", abrirFeriados);
botonAgregarFeriado.addEventListener("click", agregarFeriado);
botonCerrarFeriados.addEventListener("click", () => {
  dialogoFeriados.close();
  // Si la grilla de sesiones sigue abierta detrás, refleja los cambios de
  // feriados de inmediato, sin tener que volver a generarla.
  actualizarResaltadoFeriados();
});
