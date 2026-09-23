# Instrucciones para Claude en este repo

## Depurar fallos de Playwright contra Blackboard / Gestión Docente

Este proyecto solo funciona con selectores confirmados contra el HTML real
(ver los comentarios "confirmado con el HTML real, no inventado" en
`willaq/anuncios/publicar.py`, `willaq/dictado/publicar.py`, etc.). Cuando
algo falla ahí (un selector que ya no encuentra nada, un flujo que no hace
lo que debería, un error tipo "no se encontró X"), **no adivines
selectores ni "arregles a ciegas"**: cuando el usuario reporte un error,
**por defecto levanta tú mismo el navegador de inmediato y confírmalo en
vivo**, sin pedirle antes texto de error, HTML ni permiso — ya está dado
de forma permanente para este repo. Pedirle que copie HTML por DevTools
es un último recurso, solo si tras mirar en vivo (outerHTML, screenshots,
locators) sigue sin quedar claro qué pasó.

Antes de levantar el navegador:
- **Comprueba que el panel no esté corriendo** (`netstat -ano | grep
  :5000` o revisa si hay un proceso `python` con el panel activo). El
  perfil de navegador persistente (`datos/perfil_navegador/`) solo admite
  una instancia de Chromium a la vez: si el panel del usuario sigue
  abierto, lanzar otro navegador contra ese mismo perfil puede chocar con
  su sesión activa. Si está corriendo, pide que lo cierre (Ctrl+C) antes
  de continuar — eso sí pregúntalo, pero no pidas permiso para usar el
  navegador en sí.
- Escribe scripts de prueba en el **scratchpad** (nunca en el repo),
  importando las funciones y constantes reales del proyecto
  (`from willaq.anuncios import publicar as pub`, etc.) para probar la
  lógica de verdad, no una reimplementación aparte.
- Usa `headless=False` en tus scripts de prueba para poder ver qué pasa
  (independiente de `MOSTRAR_NAVEGADOR`, que es solo para la app en uso
  normal).
- Para inspeccionar un elemento nuevo, imprime `outerHTML`, cuenta
  locators candidatos, o saca un screenshot — no asumas la estructura.
- Itera: corre, lee el error/diagnóstico real, ajusta el selector en el
  código del proyecto (no en el script de prueba), vuelve a correr.
- Si la acción es destructiva (borrar algo real en Blackboard/Gestión
  Docente), primero valida en un curso/anuncio de prueba y avisa antes de
  dejarlo correr contra algo que le importe al docente.

## Cosas ya aprendidas sobre el Blackboard Ultra de Cibertec (para no
## volver a descubrirlas a ciegas)

- Los menús de "más opciones" (los tres puntos) son de Material UI: cada
  opción trae su propio `data-analytics-id` (ej.
  `course.announcements.listPanel.listItem.delete.button`).
- Los diálogos de **confirmación** que abren esas opciones (por ejemplo,
  "¿Eliminar anuncio?") son de **Fluent UI** (clases `ms-Dialog-*`), NO
  tienen `role="dialog"` como el resto del panel, así que
  `get_by_role("dialog")` no los encuentra. Hay que ubicarlos por su
  propio `data-analytics-id` (ej.
  `course.announcements.listPanel.listItem.deleteDialog.confirm.button`).
- El botón "Crear anuncio" (`data-analytics-id="course.announcements.listPanel.create.button"`)
  aparece **dos veces a la vez** en el DOM cuando el curso todavía no tiene
  ningún anuncio (el ícono de la barra superior + el botón grande dentro
  del panel "Anuncie algo a su clase"), ambos con el mismo
  `data-analytics-id`. Un locator sin `.first` sobre ese selector explota
  con "strict mode violation" en cursos sin anuncios (aunque funcione bien
  en cursos que ya tienen alguno). Siempre usar `.first` con ese selector.
- `pagina.goto(...)` sin `wait_until` espera el evento "load" por defecto
  (30s de timeout), pero Blackboard mantiene conexiones de red abiertas de
  fondo y a veces tarda ~26s en llegar a "load" — al borde del timeout, y
  a veces lo supera de verdad ("Timeout 30000ms exceeded... waiting until
  \"load\""). El DOM está listo mucho antes. Usar siempre
  `wait_until="domcontentloaded", timeout=60_000` en los `goto()` hacia
  Blackboard (mismo patrón ya usado en
  `willaq/autenticacion/gestion_docente.py` y `willaq/notas/recursos.py`).
- Al entrar a la página de contenido de un curso (`/outline`) que tiene
  anuncios sin leer, Blackboard muestra solo (sin pedirlo nadie) un modal
  "Nuevos anuncios del curso" que tapa toda la pantalla. Un `.click()`
  normal de Playwright sobre algo detrás de ese modal (por ejemplo, el
  botón de opciones de Collaborate) falla con "elemento intercepta
  pointer events" sin mencionar el modal para nada, aunque el botón de
  destino siga "visible". Hay que cerrarlo primero con su botón
  `data-analytics-id="course.announcements.modal.close.button"` (ver
  `_cerrar_modal_anuncios_nuevos` en `willaq/dictado/publicar.py`). Pasa
  sobre todo justo después de generar anuncios nuevos en ese curso.
- Las listas largas (anuncios, etc.) son **virtualizadas**: solo
  renderizan ~10 filas a la vez, aunque haya muchas más ("Se muestran 10
  anuncios de un total de 28..."). **Nunca uses la cantidad de filas
  renderizadas para saber si una acción (como borrar) funcionó**: al
  quitar una, Blackboard rellena el hueco con la siguiente fila cargada,
  así que el conteo de filas se queda igual aunque sí haya funcionado. Hay
  que comparar el texto "de un total de N" (`span[role="status"].sr-only`)
  antes y después.

## Cosas ya probadas y descartadas en el panel propio (willaq/web)

- **No ocultar el texto nativo de `<input type="date">` con CSS**
  (`color: transparent` + superponer un `<span>` propio encima). Se probó
  para forzar que se vea dd/mm/aaaa en vez de mm/dd/aaaa (que depende del
  idioma del navegador, no de esta app ni de `lang`): rompe el resaltado
  que Chrome dibuja sobre el segmento con foco (es un fondo, no texto, así
  que "color: transparent" no lo tapa) y el comportamiento del doble clic.
  Confirmado con el usuario probándolo en vivo ("si lo selecciono no se
  sombrea", "si le doy doble click se deforma"). La solución que quedó:
  dejar el `<input type="date">` totalmente intacto y agregar, al lado (no
  encima), un `<span class="fecha-legible">` de solo lectura con la fecha
  en día/mes/año (ver `conectarFechaLegible`/`crearFechaLegible` en
  `willaq/web/static/app.js`). Si se necesita garantizar dd/mm/aaaa de
  verdad en el campo mismo (no solo al lado), la única vía real es
  reemplazar el `<input type="date">` por un `<input type="text">` con
  máscara propia y un selector de calendario hecho a mano — no un truco de
  CSS sobre el nativo.
