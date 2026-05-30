# HANDOFF v2 — Build High School Schedules
**Fecha:** 2026-05-30 (segunda iteración del experimento)
**Cliente:** The Columbus School · Medellín, Colombia · año académico 2026-2027
**Nivel:** High School (HS) — grados 9, 10, 11, 12

> Self-contained. No leas otros directorios. Lee `context/round_1_lessons.md` ANTES de empezar — describe los errores del experimento anterior para que no los repitas.

---

## ⚠️ LEE ESTO PRIMERO

Esta es la **segunda corrida** del experimento. La primera corrida (2 agentes: OR-Tools y Rust) **falló las validaciones** con cientos de violaciones de constraints duros, a pesar de reportar buenos números de cobertura.

**No vas a "ganar" por tener más cobertura.** El ganador es quien entrega el output que (a) respeta TODAS las hard constraints, (b) tiene buena cobertura, (c) cumple el esquema exacto. Si rompes un solo hard constraint, tu output queda descalificado.

**Pre-flight obligatorio:** antes de entregar tu CSV, **DEBES correr `validate.py`** (incluido en este folder). Si reporta cualquier violación de hard constraint, NO entregues — corrige primero.

---

## Tu tarea

Dadas las **secciones existentes** (Master ya cerrado: curso, profesor, aula y slots son fijos) y las **solicitudes de cursos por estudiante**, asigna cada estudiante HS a las secciones que satisfagan su request respetando TODAS las restricciones.

**Entregable único:** un archivo CSV llamado **`student_schedules_friendly.csv`** con las **12 columnas exactas** especificadas abajo.

---

## ⚠️ Schema EXACTO (12 columnas, en este orden)

```
StudentID,StudentName,Grade,CourseID,CourseName,SectionID,Period,Slots,TeacherID,TeacherName,RoomID,RoomName
```

| # | Columna | Fuente | Obligatorio |
|---|---|---|---|
| 1 | `StudentID` | `students.csv` → `student_external_id` | ✅ |
| 2 | `StudentName` | `students.csv` → `student_name` | ✅ NO dejar vacío |
| 3 | `Grade` | `students.csv` → `grade` (int 9-12) | ✅ |
| 4 | `CourseID` | `sections.csv` → `course_id` | ✅ |
| 5 | `CourseName` | `courses.csv` → `name` (lookup) | ✅ NO dejar vacío |
| 6 | `SectionID` | `sections.csv` → `section_id` | ✅ DEBE existir en sections.csv |
| 7 | `Period` | número 1-N que enumera conjuntos distintos de slots — ver nota | ✅ |
| 8 | `Slots` | **COPIAR EXACTAMENTE** de `sections.csv` → `slots` | ✅ |
| 9 | `TeacherID` | **COPIAR EXACTAMENTE** de `sections.csv` → `teacher_id` | ✅ (puede ser vacío si la sección no tiene profesor) |
| 10 | `TeacherName` | `teachers.csv` → `teacher_name` (lookup por teacher_id) | ✅ NO dejar vacío si TeacherID existe |
| 11 | `RoomID` | **COPIAR EXACTAMENTE** de `sections.csv` → `room_id` | ✅ (puede ser vacío) |
| 12 | `RoomName` | `rooms.csv` → `name` (lookup por room_id) | ✅ no dejar vacío si RoomID existe |

**Sobre Period (col 7):** numera 1..N enumerando conjuntos únicos de `slots` que aparecen en `sections.csv`. Dos secciones con los mismos 3 slots comparten Period. No hay autoridad externa — solo debe ser consistente dentro de tu output.

**ANTI-FAIL del experimento anterior:** ambos agentes entregaron CSV con SOLO 9 columnas (omitieron Period, RoomID, RoomName) y dejaron StudentName/TeacherName vacíos. **Esto es descalificatorio.**

---

## HARD CONSTRAINTS (14 reglas — violar 1 invalida el output)

### Reglas básicas

**H1. No double-booking del estudiante.** Ningún estudiante con dos secciones que compartan slot. **Excepción: ver H8 (Term pairs).**

**H2. Capacidad.** `count(estudiantes asignados a S) <= S.max_size`.

**H3. Grade filter (SOFT en este experimento).** Idealmente `student.grade` debe estar en `courses.grade_levels`. **PERO** los datos del colegio tienen ~300 requests donde el grade_levels no coincide con el grado del alumno (ej: G1203 "Español 11" tiene grade_levels="12" pero 88 G11s lo pidieron — la columna grade_levels en estos casos está stale). **Cuando un curso está en el request del alumno, la decisión del colegio manda sobre grade_levels.** H6 (curso en request) es el gate real. `validate.py` reporta H3 como warning, no fatal.

**H4. Cursos requeridos (con matiz).** Todo curso `is_required=True` del request DEBE asignarse... **a menos que sea estructuralmente imposible**. Hay 12 pares conocidos donde el curso requerido tiene secciones existentes con cupo libre pero los 3 slots de cada sección chocan con cursos que el alumno ya tiene en su horario. La lista está en `context/known_impossible_cases.md`. Omitir esos pares es legítimo (no se cuenta como violación). Omitir CUALQUIER OTRO required SÍ es violación.

**H5. Master fijo (CRÍTICO — fallaron ambos agentes anteriores).** **NO inventes, NO modifiques.** Cada fila de tu output debe tener (SectionID, Slots, TeacherID, RoomID) que coincidan EXACTAMENTE con `sections.csv`. No puedes mover slots ni cambiar profesores/aulas. Lee `sections.csv` literalmente.

**H6. Solo cursos solicitados.** Un estudiante NO puede ser asignado a un curso que no está en su `course_requests`.

**H7. Una sección por curso por estudiante.** Si un alumno toma `H0904`, va a UNA sección de `H0904`, no a varias.

### Reglas relacionales (lee `context/constraints.md` para detalles)

**H8. Term pairs** (`course_relationships.csv`, code='Term'). 1 par: I1212↔I1213. Pueden compartir slot legalmente. Si un alumno toma ambos, sufijos deben coincidir (`I1212.1` con `I1213.1`).

**H9. Simultaneous pairs** (6 pares). Cursos en mismo slot intencionalmente. Un alumno NO toma ambos.

**H10. Teacher Assistants** (`teacher_assistants.csv`, 27 TAs). Si un alumno es TA, su asignación para ese curso DEBE ser con el `target_teacher_id` específico.

**H11. Teacher avoid** (`teacher_avoid.csv`, 11 reglas). Alumno NO con profesor prohibido.

**H12. Student pair constraints** (`student_pair_constraints.csv`, 161 pares). `separate` = no compartir sección. `together` = compartir si toman el mismo curso.

### Política

**H13. AP no se sustituye por curso regular.** (Aplica solo si tu algoritmo intenta sustituir cursos — si solo asignas requests, no aplica.)

**H14.** = H7 (una sección por curso).

---

## SOFT CONSTRAINTS (afectan ranking, no descalifican)

**S1. Cobertura.** Maximizar (student, course) pairs asignados.

**S2. Balance.** Diferencia ≤ 3 entre la sección más llena y más vacía del mismo curso.

**S3. Weighted placement.** Pesos en `student_priorities.csv` y `course_flexibility.csv`:
```
PRIORITY_WEIGHTS = {'A':10000, 'B':1000, 'C':100, 'D':10, 'F':1}
FLEXIBILITY_WEIGHTS = {'A':1, 'B':2, 'C':5, 'D':50, 'F':500}  # invertida intencionalmente
weight(student, course) = PRIORITY * FLEXIBILITY
```
Cuando dos alumnos compiten por el último cupo, prioriza el de mayor peso.

**S4. Co-planning preferences** (`co_planning_options.csv`). Informativo.

**S5. E3 reservado** para Advisory. No poner académicos en E3.

---

## 🎯 Baseline conocida

Nuestra solución actual respetando todas las hard constraints alcanza:
- **497/509 students complete = 97.64%**
- **4,597/4,610 requests satisfied = 99.72%**
- **Cero violaciones "commit"** (double-booking, capacity, master mismatch, teacher_avoid, pair, TA, request, dup-course)
- **12 violaciones "structural"** (cursos requeridos imposibles de colocar — listados en `context/known_impossible_cases.md`)

**Aclaración importante sobre "zero violations":**

Cuando decimos "zero violations", nos referimos a **commit violations** — cosas que tu output activamente comete (double-booking, exceder capacidad, etc.). Las **structural violations** son cursos requeridos que NO PUDISTE colocar porque no existe asignación legal (lista cerrada de 12 casos en `known_impossible_cases.md`). Omitirlos es la única salida legal y NO cuentan como violación.

**Si tu output reporta >97.64% cobertura PERO comete hard violations, está hacieno trampa.** El problema tiene un techo estructural: 12 alumnos con cursos rígidos cuyos slots no encajan. Llegar a 100% requiere abrir nuevas secciones (prohibido por H5).

**Si tu output tiene cobertura significativamente menor (<95%) y cero violaciones**, está mal optimizado. La solución existe.

**Si tu output evita los 12 known-impossible cases y entrega 0 commit violations, igualaste la baseline.**

---

## Datos de entrada (`data/`)

### Core (necesarios para construir output)

| Archivo | Filas | Para qué |
|---|---|---|
| `students.csv` | 509 | Quiénes (id, nombre, grado) |
| `courses.csv` | 74 | Catálogo (dept, required, AP, grade_levels) |
| `sections.csv` | 248 | **MASTER FIJO** — slots, teacher, room |
| `course_requests.csv` | 4,610 | Qué cursos pidió cada alumno |
| `teachers.csv` | 48 | Lookup de nombres + dept |
| `rooms.csv` | 38 | Lookup de nombres + tipo |

### Constraint tables

| Archivo | Filas | Constraint |
|---|---|---|
| `course_relationships.csv` | 7 | H8 (Term) + H9 (Simultaneous) |
| `teacher_assistants.csv` | 27 | H10 |
| `teacher_avoid.csv` | 11 | H11 |
| `student_pair_constraints.csv` | 161 | H12 |
| `student_priorities.csv` | 509 | S3 |
| `course_flexibility.csv` | 132 | S3 |
| `co_planning_options.csv` | 40 | S4 |
| `system_rules.csv` | 10 | meta |
| `course_equivalencies.csv` | 0 | n/a (HS vacío) |

---

## Estructura de horario

- 5 días (A-E) × 5 bloques (1-5) = **25 slots** únicos
- Notación: `<día><bloque>`, ej. `A2` = lunes bloque 2
- Cada sección académica ocupa **3 slots**; Advisory ocupa 1 (E3)
- Cada estudiante tiene 25 slots posibles; típicamente 2-4 quedan libres

---

## ⚙️ Pre-flight obligatorio

Antes de entregar tu CSV, **DEBES correr `validate.py`**:

```bash
python validate.py student_schedules_friendly.csv
```

`validate.py` chequea:
- Schema (12 columnas exactas, nombres correctos, no nulls indebidos)
- H1 (double-booking con excepción Term)
- H2 (capacidad)
- H3 (grade filter — warning, no fatal)
- **H4 (required missing — distingue "expected" vs "unexpected"; los 12 known-impossible se reportan separados)**
- H5 (Master mismatch — Slots/Teacher/Room coinciden con sections.csv)
- H6 (cursos del request)
- H7 (una sección por curso)
- H10, H11, H12 (relacionales)
- Coverage report

**Si `validate.py` reporta CUALQUIER hard violation, corrige antes de entregar.**

(El script no verifica todo perfecto — es first-pass; nosotros aplicamos verificación más estricta. Pero pasar `validate.py` es necesario, no suficiente.)

---

## Errores comunes (del experimento anterior)

**Lee `context/round_1_lessons.md` para ejemplos concretos.**

Resumen:
1. **Schema incompleto** (9 cols en vez de 12, nombres vacíos) — DESCALIFICA.
2. **Inventar slots/profesores/aulas** — H5 violation. El Master NO se toca.
3. **Asignar a cursos fuera del grado del alumno** — H3 violation. Filtra por `grade_levels`.
4. **Optimizar cobertura ignorando constraints** — invalid output. La cobertura SIN violaciones es el objetivo.
5. **Hallucinar SectionIDs** — el output debe usar IDs que existen en `sections.csv`.

---

## Cómo entregar

1. Lee `context/round_1_lessons.md` (errores del primer experimento).
2. Lee `context/constraints.md` (detalle de cada constraint con casos).
3. Lee `context/glossary.md` si necesitas aclarar términos.
4. Implementa tu enfoque (Python + pandas/OR-tools, lo que quieras).
5. Corre `validate.py` sobre tu output. **Si falla, corrige.**
6. Entrega `student_schedules_friendly.csv` en la raíz del workspace de salida.

**No produzcas otros entregables.** Solo el CSV.

---

## Filosofía del experimento

No estamos buscando un solver más rápido o más sofisticado. **Estamos buscando un solver que sea correcto** — que respete las reglas del colegio y los constraints académicos reales. Una solución 95% correcta legítima vale más que una 98% que viola reglas. El sistema actual del colegio está en 97% legal; igualarlo o mejorarlo PRESERVANDO LA LEGALIDAD es el reto.
