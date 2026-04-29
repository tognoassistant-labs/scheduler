# Preguntas para Columbus — necesarias para subir este horario

Este documento agrupa las preguntas que **bloquean directamente la importación del horario adjunto** a su instancia de PowerSchool y al LMS. Todas son sobre el formato de los datos del horario o las reglas de programación que aplicamos. No incluye preguntas de alcance futuro, gobernanza ni decisiones estratégicas — esas se manejan por separado.

> _English version: see `01_QUESTIONS_FOR_COLUMBUS_en.md` (same numbering)._

---

## A. Formato de los datos en el bundle (afectan la importación a PowerSchool)

Sin estas respuestas, los CSVs en `HS_2026-2027_real/powerschool_upload/` pueden subirse pero podrían fallar la importación o crear secciones mal vinculadas en su instancia de PowerSchool.

| # | Pregunta | Por qué importa | Dónde está hoy en el bundle |
|---|---|---|---|
| A1 | ¿La columna `SchoolID` debe contener el **número** de escuela de Columbus en PowerSchool, o el nombre? Hoy el bundle usa el nombre `"Columbus High School"`. | PS típicamente espera un número entero (ej. `1234`). El nombre puede causar fallo de importación. | `ps_sections.csv` columna `SchoolID` |
| A2 | ¿El formato de la columna `Period` debe ser `P01..P08` + `ADV` (lo que generamos), o tokens de día-bloque como `A1,D2,B4` (lo que tenemos en `Slots`)? | PS instancias varían en cómo representan el `Expression`. | `ps_sections.csv` columnas `Period` y `Slots` |
| A3 | ¿Qué `TermID` real espera PS para el año 2026-2027 en su instancia? Hoy enviamos el string `"2026-2027"`. | PS usualmente vincula secciones a un Term object con un ID específico (ej. `2700`). | `ps_sections.csv` y `ps_enrollments.csv`, columna `TermID` |
| A4 | ¿Los `CourseID` que generamos (`ALGEBRA_I_9`, `AP_CALCULUS_`, `ESPAÑOL_LITE`, etc.) **coinciden** con los `Course_Number` que Columbus ya tiene en PS, o necesitan mapeo? | Si no coinciden, las secciones no se vincularán a cursos existentes y aparecerán como cursos huérfanos. | `ps_sections.csv` y `courses.csv` columna `CourseID` |
| A5 | ¿Los `TeacherID` (`T_RODRIGUEZ_`, `T_ARCILA_FER`, etc.) coinciden con `Teacher_Number` en PS, o necesitan mapeo a IDs reales? | Mismo problema: si no coinciden, los docentes aparecen como nuevos en lugar de los existentes. | `ps_sections.csv` columna `TeacherID` |
| A6 | ¿Los `StudentID` que usamos (`28026`, `100052`, etc., tomados de la columna `ID` del xlsx) son los `Student_Number` reales en PS, o necesitan mapeo? | Sin coincidencia, las matrículas no se vinculan a expedientes existentes. | `ps_enrollments.csv` columna `StudentID` |
| A7 | ¿Los `RoomID` (`R901_0`, `R922_0`, etc.) coinciden con los IDs de salones en PS, o son sólo etiquetas internas? | Si no coinciden, los salones aparecen como nuevos. | `ps_sections.csv` columna `RoomID` |
| A8 | ¿Existe un **sandbox o instancia de prueba** de PowerSchool donde podamos hacer un dry-run antes de importar a producción? | Probar primero en sandbox es la práctica estándar y evita romper datos reales. | — (decisión externa) |
| A9 | ¿Quién es el contacto en Columbus IT que puede dar credenciales/URL del sandbox? | Sin este contacto, A8 no avanza. | — (decisión externa) |

## B. Reglas reales de Columbus que aplicamos al solver

Estas son las reglas que el motor usó para producir el horario adjunto. Si alguna no coincide con la realidad de Columbus, hay que re-correr el solver con la regla corregida.

| # | Pregunta | Cómo se manejó en este horario |
|---|---|---|
| B1 | ¿Cuál es la **lista autoritativa de cursos requeridos por grado**? Hoy usamos heurística: el nombre del curso contiene "Required" o termina en el número del grado. | `Course.is_required` en el modelo. |
| B2 | ¿La **matriz de comportamiento** (separaciones / agrupaciones) que leímos de la pestaña `Student Groupings` está completa, o hay reglas documentadas en otro lugar? | 51 separaciones + 42 agrupaciones leídas del xlsx, todas respetadas en el horario. |
| B3 | ¿El tope de **clases consecutivas para docentes** debería ser 4 o 5? Auto-relajamos a 5 cuando algún docente tiene 7+ secciones (caso real Columbus). | Con valor 4, el horario era infactible: 3 docentes con 7 secciones + 5 bloques/día = uno de los días siempre lleno. Cambio a 5 lo hace factible. |
| B4 | ¿La asesoría (Advisory) **siempre** está fija en E3, para todos los grados? | Sí, asumido en este horario (igual al horario actual de Columbus 2025-26). |
| B5 | ¿El balance de tamaño de secciones de **≤3 estudiantes** es absoluto o aspiracional? Si es aspiracional, ¿qué KPI prefieren sacrificar para llegar a 3? | Hoy llegamos a balance=4 con 97.5% electivas 1ª opción. Para llegar a 3 hay un trade-off documentado en `02_KPI_REPORT.md`. |
| B6 | ¿Los `CourseRequest` tienen rangos correctos (rank 1 = primera opción, rank 2 = alternativa)? Detectamos que los "Optatives" se interpretaban mal antes — confirmar lectura final del xlsx. | Lectura del xlsx con la convención: rank=1 si NO está marcado como "Electives Alternative N", rank=2 si sí lo está. |

## C. Verificaciones que recomendamos hacer ANTES de importar a producción

Estas son tareas concretas que el equipo de Columbus debe hacer en sandbox antes de tocar producción:

1. **Importar `ps_sections.csv` a sandbox** y confirmar que las 234 secciones aparecen vinculadas a los cursos correctos.
2. **Importar `ps_enrollments.csv` a sandbox** y verificar que ~3-5 estudiantes muestreados al azar tienen el horario correcto.
3. **Validar el formato `Period`/`Expression`** generando un reporte de schedule en sandbox y comparando con el formato esperado por la instancia.
4. **Verificar que los códigos de salones existen** en sandbox antes de importar.
5. **Hacer un demo run con 1-2 coordinadores** revisando `HS_2026-2027_real/horario_estudiantes/student_schedules_friendly.csv` para captar discrepancias antes que un padre/estudiante lo haga.

---

**Convención:** cada vez que respondan una pregunta, marcar `✅` en la tabla con la fecha. Las preguntas sin marcar siguen siendo bloqueadoras de la importación.
