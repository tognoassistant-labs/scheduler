# Preguntas para Hector — 2026-04-26 continuation session

Las "big decisions" que encontré y dejé para ti. Seguí adelante con todo lo que sí podía hacer; estos requieren tu criterio.

---

## Decisión 1 — Slow regression test calibration drift  ✅ RESUELTA 2026-04-26

**Hector decidió: Opción 1** — aceptar y documentar el slow test como "indicator only, not gate."

**Aplicado:**
- `README.md` Tier 2 Tests section actualizado: encabezado "INDICATOR ONLY, NOT A RELEASE GATE"; comentario explica que un fail no bloquea release.
- `README.md` "Known test footguns" subsection actualizado: "Per Hector decision 2026-04-26: this slow test is an indicator, not a release gate."
- `pyproject.toml` ya tenía `-m "not slow"` por default → no requiere cambio. El test sigue siendo opt-in.

No se tocaron tolerancias, golden snapshot, ni código del solver. La política está documentada para futuras sesiones.

---

### Original (kept for context):

**El issue:**
`tests/test_scenarios.py::test_golden_default_preset_tiny` (marker `slow`, opt-in, ~2.5 min) está fallando en este Linux con Python 3.12.3 + ortools 9.12.4544. El golden snapshot fue capturado esta mañana 05:39 con la **misma versión de código** (verificado por hash de `master_solver.py`, `student_solver.py`, `scenarios.py`, `sample_data.py` — todos sin tocar).

**Patrón observado en 2 corridas consecutivas:**
- Corrida A (06:06): `electives_priority` -4.2pt, `lexmin_mode` -3.3pt en first-choice; tolerancia documentada es ±3.0pt. Excede en ~1.2pt.
- Corrida B (06:09): mismo drift PLUS `cap_27` y `tight_balance` flipearon FEASIBLE→INFEASIBLE.

El **fast suite** (106 tests, budgets más grandes: master 60s, student 240s) corre **rock-solid 106/106** en ambas corridas. Es estabilidad solo del slow test.

**Diagnóstico:**
El slow test usa budgets muy ajustados (master 15s, student 30s) precisamente porque está calibrado para el ciclo CI rápido. Con `num_search_workers=4` sin `random_seed` en el student solver, el espacio de búsqueda está sujeto a contención de CPU. En esta máquina, esa contención se traduce a >±3pt de drift y, en el peor caso, a INFEASIBLE en escenarios borde como `tight_balance`.

**Por qué no toqué nada:**
- No regenerar el golden enmascararía un bug solver real si lo hubiera (lección codificada en el skills log).
- No ampliar la tolerancia tampoco — eso debilita el test sin investigar la causa raíz.
- No cambiar el solver — "big decision" per el contrato.

**Tu decisión, 3 opciones (creciente en complejidad):**
1. **Aceptar y documentar**: declarar el slow test "indicator only, not gate" y deselectarlo del CI. Ya está opt-in (`-m slow`); basta agregar una nota en README. Costo: 5 min. Riesgo: nunca más detectamos un solver bug que se manifieste solo en este test.
2. **Re-run hasta 3× antes de fail**: cambiar el slow test para correr el preset 3 veces y solo fallar si 3/3 fallan. Costo: 30 min. Riesgo: enmascaramos drift sistemático.
3. **Investigación profunda**: capturar un nuevo golden con esta máquina+versión, ver si la drift desaparece, y si así fuera, documentar que el golden es per-machine. Costo: 1-2h. Riesgo: complejidad de testing infra.

**Mi recomendación:** Opción 1 hasta May 1; revisitar después. El demo no usa el slow test.

---

## Decisión 2 — Pre-existing Hypothesis property occasionally fails post-HC2b  ⚠️ PARCIAL 2026-04-26

**Hector decidió: Opción 2** — subir budget a 60s.

**Aplicado:** `tests/test_hypothesis.py::test_property_solver_output_invariants` ahora usa `student_time=60` (era 25).

**Resultado:** **No fixed.** El test sigue fallando en `seed=1` con balance=4 (worst course: GOV). También probé 120s — mismo fail.

**Diagnóstico actualizado:** este NO es un problema de tiempo. En `seed=1, n=100` post-HC2b, la combinación master-shape + capacity + separations + balance K=5 no permite que GOV (6 sections) llegue a max-min ≤ 3 en NINGÚN budget razonable. Es estructural del seed.

Hypothesis lo marca como "reuse phase" — replay del seed=1 que está cacheado como falla. Aunque limpie la cache, Hypothesis lo va a re-encontrar.

**Ahora necesito tu call entre las opciones que quedan:**

1. **Aflojar la propiedad a `≤ 4`** (opción 1 original). Costo: 2 líneas en `check_invariants.py` para distinguir "seed=1-style edge case" del bug real. Riesgo: la propiedad ya no refleja exactamente el target v2 §10. **Recomendado.**
2. **Marcar el test como `xfail` con razón conocida** (opción 3 original). Costo: 1 line + docstring. Riesgo: oculta el caso indefinidamente.
3. **Investigar por qué seed=1 es estructuralmente diferente** — entender si es un artefacto del sample generator (n=100 es justo por encima del threshold de feasibility) o si hay algo más profundo. Costo: 1-2h.

**Mi recomendación nueva:** Opción 1 — la propiedad `balance ≤ 3` es una *regla aspiracional* en v2 §10; el target real es "≤3 most of the time, occasional 4 acceptable on edge cases." Loosening a `≤ 4` honra eso sin debilitar el solver. Si quieres, puedo agregar un soft-warning cuando es 4 (no fail).

El budget queda en 60s en el código actual (compromiso entre tu opción 2 y aceptar que el problema es estructural).

---

### Original (kept for context):

**El issue:**
`tests/test_hypothesis.py::test_property_solver_output_invariants` (max_examples=3) ahora falla intermitentemente:
- Corrida en batch (todos los Hypothesis tests): falla en seed=1 con `balance=4 > 3 (worst course: GOV)`.
- Corrida solo (`pytest tests/test_hypothesis.py::test_property_solver_output_invariants`): pasa.

**Diagnóstico:**
El test asume que la propiedad "todo solve exitoso produce balance ≤ 3" se cumple universalmente. Esa propiedad **era cierta** antes de HC2b (la corrección de la sala-de-Advisory aplicada ayer). HC2b shifteó el master OPTIMAL a una forma distinta; en esta nueva forma, ciertos seeds (como el 1, n=100) producen un student-solve borderline que apenas excede el target ≤3.

El test usa budgets ajustados (`student_time=25s`). Con más tiempo el balance probablemente cae a 3, pero ese cambio borraría parte del valor del test.

**El skills log lo predijo:**
> "Solver bug fixes shift the OPTIMAL solution and can break edge-of-feasibility fixtures."

**Tu decisión:**
1. **Aflojar la propiedad**: cambiar a `balance ≤ 4` (acepta el slack post-HC2b). Costo: 1 línea. Riesgo: la propiedad ya no refleja el target v2 §10 (≤3).
2. **Subir el budget**: cambiar `student_time=25s` a `student_time=60s` en este test. Costo: 1 línea. Riesgo: test más lento (~3 min Hypothesis vs ~2 min hoy).
3. **Marcar como xfail conditional**: aceptar que post-HC2b algunos seeds son borderline, no es regresión, marcar con `@pytest.mark.flaky` o documentar el caso. Costo: 5 min.
4. **Dejar como está**: la propiedad falla a veces, eso ES Hypothesis "haciendo su trabajo" — encontró un edge-case real. Documentar y seguir.

**Mi recomendación:** Opción 2 (subir budget a 60s). El test aún corre rápido y captura su intención original.

---

## Decisión 3 — La ortools que actualmente está pin-permitida (9.12.x) podría no ser la que generó el golden

**El issue:**
`requirements.txt` pinea `ortools>=9.10,<9.13`. Mi venv resolvió a 9.12.4544. El golden snapshot fue capturado esta mañana — desconocemos cuál ortools usó la sesión previa que generó el golden (puede haber sido 9.11.x o 9.12.x).

Esto **podría** explicar parte de la drift en decisión 1: si el golden se generó con 9.11.4210 y yo estoy con 9.12.4544, hay >100 commits de diferencia en el solver con potencial de cambiar trayectorias de búsqueda.

**Tu decisión:**
- ¿Quieres pinear más fino (ej. `ortools==9.11.4210`)? Garantiza determinismo de versión a costa de rigidez de despliegue.
- ¿O dejar el rango actual y aceptar la drift como costo de flexibilidad?

**Mi recomendación:** dejar el rango actual hasta May 1 (no toques lo que funciona). Para Track B (Phase 0+) considerar pin exacto.

---

## Decisión 4 — Si el agente de Columbus responde antes de que vuelvas

No tengo forma de detectar esa respuesta automáticamente desde esta sesión. Si llega antes de que la veas, va a quedar en algún canal externo (email, chat, share). 

**Mi recomendación:** establece un canal claro — "el agente de Columbus envía su JSON report a `agent_returns_here/columbus_response_<fecha>.json` o por email a Hector" — para que la próxima sesión (la que sea) sepa dónde buscar.

Por ahora, `agent_returns_here/COLUMBUS_AGENT_REPORT.md` registra honestamente "no response received."

---

---

## Decisión 5 — Conflicto entre "max consecutive = 4" (cliente) y auto-relax a 5 (código actual)

**El issue:**
Cliente B3 confirma: **`max_consecutive_classes` debe ser 4**. Pero el ingester actual (`ps_ingest.py` ~línea 666) auto-relaja a 5 cuando detecta un teacher con ≥7 secciones académicas:

```python
if max_observed_load >= 7:
    hard = HardConstraints(max_consecutive_classes=5)
```

La justificación está en el skills log (entrada 2026-04-26): con 5 bloques/día y 8 esquemas, un teacher con 7 esquemas distintos llena un día completo (pigeonhole) — **estrictamente infeasible** a max=4.

Real Columbus tiene 3 teachers con 7 secciones académicas cada uno. Si forzamos max=4 estricto, master solver returns INFEASIBLE.

**Opciones:**
1. **Mantener auto-relax** — silently ignore client B3 answer; documentar el porqué. Riesgo: cliente puede objetar.
2. **Forzar max=4 estricto** — re-ingestar puede fallar; bundle v3 tendría master INFEASIBLE para HS. NO recomendado.
3. **Pedir a Columbus que reduzca carga de los 3 teachers a ≤6 sec.** — la solución estructural correcta pero requiere coordinación.
4. **Auto-relax con mensaje al cliente** — mantener relax pero en docs y export, anotar "B3 reglamento dice 4, técnicamente este horario tiene casos a 5 por carga; revisar con coord. académica."

**Mi recomendación:** Opción 4 (mantener relax + documentar la excepción claramente para Columbus). Es la única que mantiene el horario funcional y honesto.

---

## Decisión 6 — MS sin Advisory fijo en E3

**El issue:**
Cliente B4: para HS, Advisory está fijo en E3. Para **MS, NO hay bloques fijos**, solo está fija la frecuencia de cursos.

El código actual hardcodea Advisory en Day E Block 3 vía `default_rotation()` y `HardConstraints.advisory_day=E, advisory_block=3` para AMBAS escuelas.

**Para HS:** sin cambio, el actual está correcto.
**Para MS:** habría que:
- Eliminar el "ADVISORY" cell de la rotación (o usar una rotación diferente para MS)
- Permitir que el solver coloque cualquier curso en E3 para MS
- O simplemente dejar que MS no tenga Advisory en absoluto (pareciera que MS no tiene Advisory por contexto)

**Costo de implementación:** moderado — afecta `models.BellSchedule`, `default_rotation`, master_solver assumptions sobre el slot ADVISORY.

**Opciones:**
1. **Aplazar para Track B Phase 5 (MS expansion).** Por ahora MS es PoC sintético; el bundle v2 tiene MS sintético con la misma rotación HS.
2. **Implementar ahora, antes de regenerar bundle.** Costo: ~2-3h código + tests.
3. **Implementar parcialmente: MS sin ADVISORY del todo.** Más fácil que MS con rotación distinta.

**Mi recomendación:** Opción 1 (aplazar). MS sintético en v2 funciona porque comparte rotación con HS; cambiar la estructura ahora invalida el sintético MS y agrega riesgo. Documentar como gap conocido en PRODUCTION_GAPS.md.

---

## Decisión 7 — Semántica de "Section balance ≤3"

**El issue:**
Cliente B5 (parafraseando): "Para los profesores, la cantidad de secciones por profesor es definida desde antes de acuerdo a las políticas de la escuela y la demanda en las solicitudes de los estudiantes."

Esto suena a **balance de carga docente** (cuántas secciones tiene cada teacher), NO a **balance de tamaño de sección por curso** (que es lo que el código actualmente enforce vía `max_section_spread_per_course=5`).

v2 §10 dice "Section balance deviation ≤ 3 students" — yo lo interpreté como "max-dev de tamaño de sección dentro del mismo curso ≤ 3 estudiantes". El cliente parece estar hablando de algo distinto.

**Opciones:**
1. **Mantener interpretación actual** (per-course class-size dev ≤3). Es la interpretación literal de v2 §10 y produce KPIs medibles.
2. **Reinterpretar como teacher-load balance.** Eso ya está cubierto por `SoftConstraintWeights.teacher_load_balance` (peso default 5) — pero NO es un hard constraint, es soft.
3. **Pedir clarificación al cliente.** Antes de re-pesar el solver, confirmar qué quiere decir "balance" exactamente.

**Mi recomendación:** Opción 3. La respuesta del cliente B5 es ambigua y mover esto sin confirmar puede degradar KPIs visibles para nada.

---

## Decisión 8 — "No alternates para 2026-2027"

**El issue:**
Cliente B6: para 2026-2027, **NO hay alternas**. Las solicitudes ya fueron depuradas. HS solo tiene PE como required; el resto son electives por área.

El ingester actual (`ps_ingest.py`) detecta "Electives Alternative N" en `course_group_name` y marca esos requests como `rank=2` (alternates). Para 2026-2027, todos los requests deberían ser `rank=1`.

**Opciones:**
1. **Hardcodear**: en `ps_ingest`, si `year contains "2026-2027"`, ignorar el flag de alternative (todos rank=1). Costo: 3 líneas, low risk.
2. **Agregar parámetro CLI**: `--ignore-alternates` flag (default False, true para 2026-2027). Más explícito.
3. **No cambiar código; documentar para que coord. depure data antes de ingestar.** Frágil.

**Mi recomendación:** Opción 2 (CLI flag explícito). El user que ingesta sabe el contexto y prende el flag. Más limpio que un hardcode por año.

**Implementación pendiente:** ~10 min código + 1 test. Solo procedo si tú confirmas la opción.

---

## Decisión 9 — Regenerar bundle v3 con los nuevos formatos PS

**El issue:**
Las correcciones al exporter (SchoolID 12000/13000, Period `1(A)2(B)3(C)`, TermID 3600) cambian los CSVs que se exportan. El bundle v2 (entregado a Columbus, hash `5a2932b8...46a89`) tiene los formatos VIEJOS.

Si Columbus IT corre `verify_bundle.py` sobre el bundle v2, el verifier va a pasar (porque el verifier no chequea los formatos PS específicos). Pero cuando intenten importar a sandbox, los SchoolID/Period/TermID van a fallar.

**Opciones:**
1. **Regenerar bundle v3 ahora**, subir nuevo SHA256SUM.txt, notificar a Columbus. Costo: ~30 min (re-ingestar + re-solver + re-zip + actualizar docs).
2. **Esperar a feedback del verifier corrido sobre v2** antes de re-bundlear. Riesgo: tiempo perdido si IT ya empieza dry-run.
3. **Generar v3 pero NO entregar todavía** — mantenerlo listo para cuando Columbus pida.

**Mi recomendación:** Opción 3. Tener v3 listo en `bundle_for_columbus/columbus_2026-2027_bundle_v3.zip` (co-existir con v2), y avisar a Columbus por el canal apropiado: "v2 tiene formatos PS que requerían los valores que IT confirmó; v3 los aplica. Por favor probar v3 en sandbox."

**Si dices que sí a v3, hago:**
- Regenerar bundle desde código actualizado
- Update `SHA256SUM.txt` con ambos hashes (v2, v3)
- Notas de cambio en bundle README
- NO toco bundle v2

---

---

## Decisión 10 — TermID=3600 es del año, semester, o quarter?

**El issue:**
Confirmaste que en Columbus hay **4 quarters al año (Q1-Q4)**, con **2 quarters = 1 semester**. Cliente A3 dijo "TermID real es 3600" (singular).

El exporter actual escribe `TermID=3600` en TODAS las secciones, sin importar si son year-long, semester, o quarter. Si PS espera TermIDs distintos por granularidad, el import puede meter todo a Q1 (incorrecto para cursos year-long que abarcan Q1-Q4).

**Necesito saber:**
- ¿`3600` es el TermID del **año académico completo** (un sólo ID que todos los cursos year-long usan)?
- ¿O es el TermID de **un quarter específico** (probablemente Q1) y hay 3601, 3602, 3603 para Q2/Q3/Q4 + uno separado para semester y otro para year?
- ¿El campo `Course.term: YEAR/SEMESTER/QUARTER` (que ya tenemos en models.py) debe mapearse a TermIDs distintos?

**Por qué importa para v3:**
- Si `3600` es year-level, el export actual está OK (todo va con 3600).
- Si `3600` es quarter-level, hay que: (a) aprender los IDs de los otros 3 quarters + 2 semesters + 1 year, (b) leer `Course.term` para escoger el TermID correcto por sección.

**Mi recomendación:** preguntar a IT (Juan Pablo / Luis) explícitamente qué TermID usar por categoría de curso. Por mientras, dejar `3600` para todo y NO regenerar bundle v3 hasta saber la respuesta.

**Implicación para Decisión 9 (regenerar v3):** si TermID es por-categoría, regenerar v3 con sólo `3600` puede meter todo en Q1 — eso ROMPE el import de cursos semester/year, peor que la situación actual. **Esta decisión bloquea la decisión 9.**

---

## Lo que NO hice (a propósito)

Por respeto al contrato "no big decisions alone":

1. NO regenere el golden snapshot.
2. NO modifiqué `master_solver.py` ni `student_solver.py`.
3. NO toqué el bundle (`columbus_2026-2027_bundle_v2.zip`) — hash unchanged.
4. NO reintenté cohort Hall-matching (lección clara en el skills log).
5. NO pursued (e), (f), (g), (h) del menú de prioridades — fuera de alcance MVP.

## Lo que SÍ hice (sin pedir permiso, dentro del Priority 2 + bug-fix scope)

Per START_HERE.md "Priority 2 — Hardening that doesn't change the deliverable":
1. ✅ Hypothesis property test for HC2b (ya estaba listado explícitamente en el doc)
2. ✅ Run slow regression to confirm passes (corrió, **falló** — ver decisión 1)
3. ✅ Document fast/slow split in README (listado explícitamente)
4. ✅ CLI subcommand for synthetic MS (listado explícitamente)

Plus:
5. ✅ Streamlit smoke-test (Priority 3 demo prep — `AppTest` boots clean, 6 tabs)
6. ✅ Updated `docs/scheduler_skills_log.md` con esta sesión

Después llegaron las respuestas del cliente con A1-A9 + B1-B6. Procesé los **bug fixes claros** (formatos PS demonstrably wrong → corregidos a valores confirmados):
7. ✅ `SchoolConfig.school_id` + `SchoolConfig.term_id` fields agregados (opcional, fallback al comportamiento actual)
8. ✅ `exporter._period_code(scheme)` → `exporter._expression(slots)` con format `1(A)2(B)3(C)` y `1(D-E)`
9. ✅ `ps_ingest` detecta MS vs HS por grados, setea `school_id=12000/13000`, `term_id="3600"`
10. ✅ `tests/test_reports_exporter.py` actualizado: advisory Period == "3(E)"
11. ✅ `tests/check_invariants.py` refactor: detect advisory por CourseID en vez de Period; HC1/HC2 ahora usan Slots como ground truth en lugar de Period (más robusto al cambio de format)
12. ✅ `docs/internal_pending_decisions.md` actualizado con audit trail de las respuestas del cliente

Todo aditivo, fast suite **sigue 106/106 passing**, formato Period verificado end-to-end con manual smoke run.

**No modifiqué:**
- `master_solver.py` / `student_solver.py`
- El bundle (`columbus_2026-2027_bundle_v2.zip` hash unchanged)
- La rotación / BellSchedule (decisión 6 aplazado)
- El ingester de alternates (decisión 8 esperando tu confirmación)
- El auto-relax de max_consecutive a 5 (decisión 5 esperando tu decisión)
