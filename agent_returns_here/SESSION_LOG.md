# Session log — agent that ran 2026-04-28 (HC4 + cliente feedback round)

**Started:** 2026-04-28 (after Hector forwarded cliente validation feedback)
**Total wall:** ~2 hours focused work + 30 min waiting for solve
**Mode:** autonomous, "do as much as you can"

## Context received from Hector

1. Cliente validó el bundle v2 con un agente (Juan Pablo). Reportó 4 problemas:
   - **A. Salones:** "muchos cursos al mismo salón, no al mismo tiempo pero muchos" + doc dice "salón es por profesor".
   - **B. Profesores con 5 bloques seguidos en 1-2 días.**
   - **C. Profesor "Julián Zúñiga" sin cursos.**
   - **D. Curso "Tecnología" faltando.**
   - Cliente dijo: "estuvo muy acertado, lo MÁS importante es lo de los salones."
2. Cliente confirmó respuestas A1-A9 + B1-B6 (formato PS, ambiente, reglas académicas).
3. Cliente mencionó que va a enviar archivos con CourseID/TeacherID/SectionID reales y estructura PS final.
4. Agente previo no pudo avanzar mucho por problemas de Python.

## Análisis (10 min)

Investigué el handoff continuation, las notas del agente previo, y la data real:

- **A es bug REAL** — confirmado: ejemplo Hoyos Camilo dictaba 5 secciones en 5 salones distintos en v3.
- **B es bug REAL** — confirmado por doc rfi_Reglas_Horarios_HS: max=4 estricto. Auto-relax actual a 5 va contra el doc.
- **C es FALSA ALARMA** — Julián SÍ tiene 2 secciones (AP CS A + Principles) en bundle v2; aparece como "Zuniga, Julian" (sin tildes, formato LISTADO). Probable mismatch cosmético.
- **D es FALSA ALARMA** — Technology 9 está en bundle con 3 sec, profesor John Higuita (NO Julián). Cliente posiblemente confundió.

**Encontré el doc clave:** `reference/rfi_Reglas_Horarios_HS_2026_04_22_13_46_GMT_05_00_Notes_by_Gemin.md` con las reglas exactas de salones por profesor.

## Implementación (HC4 — salón por profesor)

### Cambios en código

1. **`src/scheduler/ps_ingest.py`:**
   - **`_is_placeholder_teacher(name)`**: detecta "New X Teacher" como placeholder.
   - **Lectura de `Teacher.home_room_id`** desde columna ROOM del LISTADO MAESTRO. Sólo asigna home_room cuando:
     - El profesor NO es placeholder, Y
     - El profesor tiene exactamente 1 ROOM en LISTADO (single-room teachers).
   - **Multi-room teachers** (Sindy Margarita, varios "New X") quedan con `home_room_id=None` — flotan.
   - **Reverted auto-relax** de `max_consecutive_classes`. Ahora imprime un WARNING explícito a stderr listando los profesores con ≥7 secciones académicas y las opciones de mitigación. El operador decide.

2. **`src/scheduler/master_solver.py`:**
   - **Nueva HC4** (~líneas 73-85): cuando `Teacher.home_room_id` está set y no hay `Section.locked_room_id`, el dominio de `section_room` se restringe sólo al home_room del profesor. Se aplica antes de la creación del IntVar.
   - `locked_room_id` (operator override) sigue precediendo a HC4.

3. **Tests añadidos:**
   - `tests/test_master_solver.py::TestHomeRoom::test_home_room_pins_academic_sections` — pin academic sections a home_room.
   - `tests/test_master_solver.py::TestHomeRoom::test_home_room_unset_keeps_default_behavior` — sin home_room, comportamiento normal.
   - `tests/test_ps_ingest.py::TestMultiGradeIngest::test_full_hs_assigns_home_rooms_from_listado` — verifica ≥80% de teachers reciben home_room.
   - **Actualizado** `test_full_hs_relaxes_max_consecutive_classes` → `test_full_hs_keeps_strict_max_consecutive` (asserta que ya NO hay auto-relax y que el WARNING se imprime con el formato esperado).

### Trade-offs medidos en re-solve real Columbus full HS (510 students)

| Métrica | v3 (sin HC4) | v4 (con HC4) | Cambio |
|---|---|---|---|
| Section balance dev | 3 ✅ | 3 ✅ | = |
| First-choice electives | 98.7% | 92.7% | -6.0pt (costo del room pinning) |
| Unmet rank-1 | 38 / 510 | 214 / 510 | +176 (más estudiantes en alterna) |
| HC4 violations | n/a | **0** | ✅ |
| Profesores académicos en >1 salón | many | 4 (Sindy + 3 placeholders) | ✅ por diseño |
| Master solve time | 4s | 1.2s | -2.8s (HC4 reduce search space) |

92.7% sigue sobre el target ≥80%. Los 4 profesores en >1 salón son los floating intencionales.

**v4 PS exports en:** `scheduler/data/columbus_full_hs_v4/` (powerschool/, oneroster/, input_data CSVs).

## Lo que NO hice (a propósito)

1. **NO regeneré el bundle v2** — `bundle_for_columbus/columbus_2026-2027_bundle_v2.zip` hash unchanged. Decisión de regenerar como v3 queda para Hector.
2. **NO toqué el cliente-bundle del agente previo** (sus PS format fixes en exporter.py + ps_ingest.py — SchoolID 12000/13000, Period `1(A)2(B)3(C)`, TermID 3600 — siguen aplicados).
3. **NO ataqué el "5 bloques seguidos"** porque al pasar `max_consec=5` explícito en el script de re-solve, sigue habiendo casos. El fix verdadero requiere coordinación con cliente para reducir carga de los 3 profesores con 7 sec. Lo dejé documentado en el WARNING.

## Decisiones que requieren a Hector

Ver `QUESTIONS_FOR_HECTOR.md`. Las nuevas:

- **Decisión 11** — ¿Regenerar bundle como v3 con HC4 + PS format fixes ahora, o esperar los archivos prometidos del cliente (CourseID/TeacherID/structure) y hacer una sola regeneración v3 después?
- **Decisión 12** — Sobre los 3 profesores con 7 sec académicas (Sofia Arcila, Gloria Vélez, Clara Martínez): ¿Hector negocia con el cliente para reducirles 1 sección a cada uno (a 6) y poder honrar `max_consec=4` strict? O aceptar el override a 5 con warning explícito.

## Net result

**Bug crítico del cliente resuelto.** HC4 fuerza que cada profesor con home_room asignado en LISTADO MAESTRO use SOLO ese salón para todas sus secciones académicas. Los 5 docentes (incluido Hoyos Camilo) que el cliente reportó en múltiples salones ahora están consistentemente en uno. Trade-off mensurable en electives (-6pt), pero todos los KPIs siguen pasando.

107+ tests passing (105 fast del agente previo + 3 nuevos por HC4). Bundle v2 NO modificado.
