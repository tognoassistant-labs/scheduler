# Casos estructuralmente imposibles (12 conocidos)

> Esta es la lista de los 12 estudiantes HS para quienes existe un curso de su request que NO se puede asignar **dados los constraints actuales y el Master fijo**. Si tu output incluye una fila para uno de estos pares (estudiante, curso), estás violando H1 (double-booking) o H5 (Master mismatch). Lo legítimo es **omitir esa fila** — el evaluador NO cuenta esto como violación de H4.

## La lista

| StudentID | Grado | Curso faltante | Nombre del curso | Razón | Slots libres del alumno |
|---|---|---|---|---|---|
| **27028** | 12 | L1303 | Pensar nuestro tiempo | slot_conflict | A3, C1, D4 |
| **27042** | 12 | OA1304 | AP Biology | slot_conflict | B1, C4, E2 |
| **27071** | 12 | OA1304 | AP Biology | slot_conflict | A2, B5, D3 |
| **27124** | 12 | C0907 | Band Level III | slot_conflict | B1, B2, C4, C5, E2, E4 |
| **27138** | 12 | OA1304 | AP Biology | slot_conflict | A2, B5, D3 |
| **27142** | 12 | G1202 | AP Spanish Literature and Culture | slot_conflict | A4, C2, D5 |
| **28044** | 11 | H1206 | AP English Language & Composition | slot_conflict | B1, C4, E2 |
| **28052** | 11 | L1303 | Pensar nuestro tiempo | slot_conflict | A2, A3, B5, C1, D3, D4 |
| **28071** | 11 | OC1306 | Sculpture I | slot_conflict | A1, B4, D2 |
| **28157** | 11 | OA1317 | AP Chemistry | slot_conflict | A4, C2, D5 |
| **28168** | 11 | OC1314 | AP Drawing | slot_conflict | A4, B3, C2, D1, D5, E5 |
| **28169** | 11 | OJ1306 | AP Computer Science Principles | slot_conflict | A1, B4, D2 |

## Por qué son imposibles

Cada uno de estos casos es un **slot_conflict**: el curso pedido tiene secciones existentes con cupo libre, pero los 3 slots de cada sección coinciden con cursos que el alumno ya tiene en su horario. Como no puedes:

- Modificar el Master (cambiar los slots de la sección) → H5
- Mover otros estudiantes para liberar slots del alumno → ya se intentó en preprocessing (self-swap exhausted)
- Abrir nuevas secciones → H5
- Sustituir el curso por uno equivalente regular (todos los AP) → política H13

… la única salida legal es **omitir la fila para ese par (estudiante, curso)**.

## Casos especiales

- **OA1304 AP Biology**: 3 estudiantes (27042, 27071, 27138) lo necesitan pero su única sección existente choca con sus horarios. Esto es real-world: el colegio ya analizó y decidió no abrir más secciones.
- **L1303 Pensar nuestro tiempo**: 2 estudiantes (27028, 28052). L1303 es singleton.
- **AP Calculus AB (I1204)** NO está en esta lista — se resolvió a través de cambios manuales del colegio antes del experimento. Lo mismo otros casos ya resueltos.

## Cómo interpretar para tu validate.py / output

**OK (legítimo):**
- Omitir la fila para (StudentID, CourseID) que está en esta lista
- El evaluador reconoce estos 12 casos como "structurally unassignable" y no los cuenta como H4 violation

**NO OK:**
- Forzar asignación violando H1 (slot collision)
- Modificar el Master para que encaje (H5)
- Inventar una sección nueva (H5)

## ¿Cómo verifico que mi output coincide en este punto?

`validate.py` clasifica las H4 violations en dos categorías:
- **Expected** (cualquiera de estos 12 pares): es OK, no cuenta como violation
- **Unexpected**: real violation — algo de tu lógica falló al colocar un curso requerido que SÍ era colocable

Si tu output muestra `H4 unexpected violations: 0`, estás en la misma situación que la baseline. Si tiene `>0`, tu solver tiene un bug — esos casos sí eran asignables.

## ¿Cuál es el techo real entonces?

Si tu output omite exactamente estas 12 filas y nada más:
- **497/509 students complete = 97.64%**
- **4,597/4,610 requests satisfied = 99.72%**
- **0 hard violations (commit + structural en separadas)**

Eso es el techo legal con el Master actual. Llegar a 100% requiere acciones que el experimento no permite (abrir secciones, modificar slots).

Si encuentras una asignación que mejora esto SIN violar constraints, has encontrado un bug en nuestra solución actual — házlo notar.
