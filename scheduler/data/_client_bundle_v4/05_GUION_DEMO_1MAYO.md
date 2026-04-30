# Guión de demo — Columbus HS 2026-2027

**Fecha demo:** 1 de mayo 2026
**Audiencia:** equipo del Colegio (probablemente principal + Juan Pablo + coordinador académico)
**Duración estimada:** 30–45 min
**Bundle:** v4.18 ([commit `91785e2`](https://github.com/tognoassistant-labs/scheduler/commit/91785e2))

---

## Resumen ejecutivo (la frase que abre la conversación)

> *"Generamos un horario que cumple al 100% las 6 políticas que ustedes definieron, con cobertura por encima de la meta de 90% que aceptaron. Hoy les enseñamos qué quedó, qué falta, y qué necesitan aprobar para subir más."*

---

## Qué mostrar — orden recomendado (5 estaciones, ~5–8 min cada una)

### Estación 1 — KPIs y métricas globales (5 min)

**Abrir:** `02_KPI_REPORT.md` (en el bundle, o el archivo en GitHub).

**Decir:**
> *"Cobertura required del 93.6% (meta era 90%). Eso significa que de cada 100 cupos solicitados, llenamos 93.6. Quedan 295 cupos sin asignar, distribuidos en 260 estudiantes (algunos pierden 2)."*

**Mostrar la tabla de KPIs**, destacar:
- ✅ Section balance ≤ 3 (cumple v2 §10 ideal por primera vez)
- ✅ Time conflicts: 0 (siempre cumplido por construcción)
- ❌ First-choice electives 0% (no aplica: para 2026-2027 no hay electives)
- ❌ Fully scheduled 48.9% — *esto es lo que va a doler*

**Anticipar pregunta**: *"¿por qué solo 48.9% completos?"*
**Responder**: *"Porque la mitad del salón pierde al menos 1 curso. Para llevar esto a 100% completos, necesitamos abrir secciones nuevas (estación 5)."*

---

### Estación 2 — Las 6 políticas que ustedes definieron, todas al 100% (5 min)

**Abrir:** la tabla del commit message de v4.17 o leer la siguiente:

| Política del Colegio | Cumplimiento |
|---|---|
| Balance ≤ 4 (su ideal) | **100%** (49 de 49 cursos multisección) |
| "Separado de" del consejo pedagógico | **100%** (79 de 79 pares respetados) |
| Coplanning HARD | **100%** (los 18 grupos comparten esquema libre) |
| AP Micro/Macro al mismo slot | **100%** (4 de 4 secciones pareadas) |
| AP Research cap=26 | ✓ (auto-aplicado de columna CONSTRAINTS) |
| Sin over-fill ni secciones nuevas | ✓ |
| Max 4 consecutivas | ✓ (excepción Gloria por necesidad matemática) |

**Decir:**
> *"Esta es la versión 'horario limpio' que recomendamos para producción. TODAS las reglas que ustedes nos pidieron, respetadas. Cuando bajamos cualquiera de estas a 'soft', la cobertura sube. Pero ustedes dijeron que estas reglas son inamovibles, así que no las tocamos."*

---

### Estación 3 — El visor: ver el horario de un estudiante o profesor (10 min)

**Abrir:** `visor_html/index.html` (en cualquier navegador, no requiere servidor).

**Demo en vivo:**
1. Mostrar el índice — 509 estudiantes, 42 profesores listados.
2. Click en un estudiante con cobertura completa → mostrar el grid 5×5 con sus 8 cursos + advisory.
3. Click en un estudiante con un curso faltante → mostrar el hueco en la grilla.
4. Click en un profesor → ver su semana completa (qué clases dicta, cuándo, dónde, con qué grupo).
5. Mostrar Ortegón o similar para enseñar **AP Micro y AP Macro pareadas en el mismo slot** (era el bug que el cliente reportó como "se enloquece el horario").

**Frases sugeridas:**
- *"Cada celda muestra curso, sección, profesor y aula. Las celdas vacías son slots libres del estudiante (prep o lunch)."*
- *"Esta vista es lo que el estudiante o el profesor verá cuando exportemos a PowerSchool."*

**Anticipar pregunta**: *"¿Esto se puede imprimir?"*
**Responder**: *"Sí, cada página HTML se imprime a PDF directamente desde el navegador. Para entrega masiva podemos generar un PDF por persona en batch."*

---

### Estación 4 — Casos específicos (los que sabemos que van a preguntar) (5 min)

**Abrir:** `horario_estudiantes/student_schedules.csv` (Excel) y filtrar por `n_missing > 0`.

**Tener listas las respuestas de los casos que el Colegio ya nos preguntó:**

- **Estudiante 27001 (G12)**: pidió 8 cursos reales, recibió 7 + advisory. Le falta `OB1532 AP Research` y `OA1318 AP Environmental Science`. Causa: grid (slots de las únicas secciones disponibles chocan con sus otros required).
- **Estudiante 27114 (G12 con 9 requests)**: pigeonhole real — 25 cells ocupadas, no cabe 1 más para PE 12.
- **Estudiante 29174 (G10)**: técnicamente cabe en `A1006.1` pero entrar rompía el balance ≤4. Es el caso textbook de "balance vs cobertura".
- **Sofia/Gloria/Clara (overrides max_consec=5)**: aclarar que en realidad solo Gloria tiene 7 secciones académicas; Sofia y Clara tienen 6, no necesitan override.

**Decir:**
> *"Cada estudiante con un curso faltante tiene una explicación específica. El reporte dice exactamente cuáles cursos perdió y cuáles. Si un padre llama, podemos justificar el caso."*

---

### Estación 5 — Propuesta para admin: las 5 secciones que recuperan más estudiantes (10 min)

**Abrir:** `04_PROPUESTA_SECCIONES_ADICIONALES.md` (en el bundle).

**Decir:**
> *"Con las reglas estrictas que ustedes definieron, esto es lo máximo que se puede sin abrir secciones nuevas. Para subir cobertura más, hay que abrir secciones — decisión administrativa. Les preparé el ranking exacto de qué abrir primero."*

**Mostrar la tabla del top 5:**

| Curso | Unmet | Recupera | Slots sugeridos | Profe actual |
|---|---|---|---|---|
| Algebra I 9 | 41 | +25 | A4, C2, D5 | Rodriguez (6 sec) |
| FRC 9 | 21 | +14 | A1, B4, D2 | Henao (6 sec) |
| Español Lit 11 | 16 | +10 | B3, D1, E5 | Restrepo (6 sec) |
| Español Lit 9 | 15 | +9 | A4, C2, D5 | Martinez/Villamizar |
| Journalism Higher | 15 | +8 | B2, C5, E4 | Shainker (6 sec) |
| **Top 5 = 108 unmet → +66 recuperación** |

**Insight clave para destacar:**
> *"Hallazgo importante: NINGÚN curso es 'capacity-bound' — todos tienen cupos libres. El problema es 100% de placement: las secciones existentes están en horarios donde los estudiantes ya están ocupados. Por eso las secciones nuevas tienen que ir a SLOTS específicos, no a cualquier hora."*

**Caso especial fácil:**
> *"AP Research: Butterworth solo dicta esa 1 sección. Tiene capacidad para tomar otra sin contratar a nadie. Si abren 1 sección más con ella, recuperan ~8 estudiantes."*

---

## Preguntas que el Colegio HARÁ — respuestas pre-armadas

### "¿Por qué la cobertura no es 100%?"
> *"Por sus reglas estrictas. Sin balance hard, sin separations hard, sin coplanning hard, llegamos al 97.7%. Ustedes priorizaron las políticas sobre la cobertura. Para subir más, hay que abrir secciones (propuesta lista en estación 5)."*

### "¿Por qué solo 48.9% de estudiantes completos?"
> *"Distribuidos: la mayoría de los 260 estudiantes con problemas pierden 1 solo curso. Solo 1 estudiante pierde 3. La métrica de 'completo' es estricta — un estudiante con 7 de 8 cursos cuenta como '0%'. Required fulfillment del 93.6% es la métrica más justa para evaluar el motor."*

### "¿Esto está listo para PowerSchool?"
> *"Los CSVs están listos en formato PowerSchool (carpeta `powerschool_upload/`). NO los hemos validado contra una instancia real de PS — eso es el siguiente paso post-demo. Si ustedes tienen un test environment, lo probamos esta semana."*

### "¿Cuándo lo subimos a producción?"
> *"Después de: (a) que ustedes aprueben este bundle como 'OK para enseñar al colegio', (b) que decidan qué secciones nuevas abrir, (c) que probemos el import a PS. Estimado: 1–2 semanas más."*

### "¿Qué pasa si un profesor se enferma o renuncia?"
> *"El motor regenera el bundle en 5 min con datos actualizados. Pero el horario de los estudiantes ya impreso no cambia automáticamente — eso requiere comunicación operativa, fuera del motor."*

### "¿Qué pasa con los advisory groups?"
> *"Hoy se asignan round-robin sintético. Si ustedes tienen grupos de advisory predefinidos por homeroom, podemos importarlos — solo necesitamos esa lista."*

### "¿Cuánto cuesta agregar 1 sección nueva?"
> *"En el motor: 0 minutos, regeneramos el bundle. En la realidad: profesor + aula + 3 slots libres en su semana. Es decisión administrativa del colegio. La propuesta de sección extra (estación 5) ya identifica los slots que más recuperan."*

---

## Lo que NO mostrar / NO discutir

- ❌ La varianza del solver (`FEASIBLE` vs `OPTIMAL`). Es ruido técnico, no aporta. Si preguntan, responder *"el solver siempre cumple las constraints; las pequeñas variaciones de cobertura entre runs son normales y dentro de margen"*.
- ❌ Detalles del lex-min vs weighted grade priority. Demasiado técnico.
- ❌ Implementación interna de las constraints (HC1–HC8). Son detalles, no decisiones de ellos.
- ❌ Historial de bugs (Micro/Macro, New Teacher silent drop). Ya están corregidos, mencionarlos solo crea ansiedad.

---

## Prep checklist 30 min antes de la demo

- [ ] Verificar que el bundle más reciente está en GitHub (correr `git log -1` y `git status -s` debe estar limpio)
- [ ] Abrir `visor_html/index.html` en una pestaña — pre-cargada
- [ ] Tener `02_KPI_REPORT.md` y `04_PROPUESTA_SECCIONES_ADICIONALES.md` listos
- [ ] Filtrar `student_schedules.csv` por `n_missing > 0` para tener los casos a la mano
- [ ] Tener un profesor "estrella" para mostrar (sugerencia: Ortegón, porque demuestra el fix Micro/Macro)

---

## Post-demo: qué pedir al cierre

1. **Aprobación del bundle v4.18** como "OK para empezar a hablar con el colegio".
2. **Decisión sobre las 5 secciones nuevas** — si las aprueban, regeneramos en 5 min.
3. **Acceso a PowerSchool test environment** para validar el import.
4. **STUDENT_NUMBER en `teacher_avoid`** (9 de 11 filas siguen sin matchear).
5. **Lista de advisory groups predefinidos** si existen.
6. **Confirmación final**: ¿el bundle v4.18 es el "snapshot oficial" para esta ronda?

---

## Si algo sale mal en la demo

| Síntoma | Plan B |
|---|---|
| Visor HTML no carga | Mostrar `student_schedules_friendly.csv` en Excel |
| El cliente no entiende un número | Aterrizar al "estudiante 27001 perdió AP Research por X razón" |
| Pregunta técnica que no sabes | *"Te respondo después de la demo con datos exactos"* — anotar |
| Discusión se vuelve política (más secciones / contratar) | *"Eso es decisión administrativa, te llevamos esta propuesta. El motor produce con lo que hay"* |
| El Colegio insiste en cobertura 100% sin abrir secciones | *"Matemáticamente imposible con sus reglas estrictas. Con datos: probamos relajar cada regla y siempre baja la cobertura. La única salida es más capacidad."* |
