# Constraints — referencia detallada

Esta es la referencia completa con ejemplos. `HANDOFF.md` tiene el resumen; aquí están los matices y los casos comunes.

---

## HARD CONSTRAINTS

### H1 — No double-booking de estudiante

**Regla:** ningún estudiante puede tener dos secciones que compartan algún slot.

**Excepción:** ver H8 (Term pairs).

**Ejemplo de violación:** alumno `27042` asignado a sección con slots `A2;B5;D3` Y a otra con slots `A2;C1;E4`. Ambas usan `A2` → físicamente imposible.

**Verificación:**
```python
slots_taken = set()
for course_id, section_id in student_assignments[student]:
    for slot in sections[section_id]["slots"].split(";"):
        if slot in slots_taken:
            VIOLATION
        slots_taken.add(slot)
```

### H2 — Capacidad de sección

**Regla:** `len(estudiantes asignados a S) <= S.max_size`

`sections.csv` columna `max_size` (típicamente 25).

### H3 — Grade filter

**Regla:** `student.grade ∈ courses.grade_levels`

`courses.grade_levels` es CSV:
- `"9"` → solo G9
- `"11,12"` → G11 y G12
- `""` (vacío) → ningún grado (curso inactivo)

**Ejemplo de violación:** alumno G9 asignado a curso `OA1317` (AP Chemistry) cuyo `grade_levels="11,12"`. Académicamente imposible.

**Verificación:**
```python
allowed_grades = [int(g) for g in courses[course_id]["grade_levels"].split(",") if g.strip()]
if student.grade not in allowed_grades:
    VIOLATION
```

### H4 — Cursos requeridos

**Regla:** todo `course_request` con `is_required=True` DEBE asignarse.

Cursos requeridos típicos: Math, English/Spanish del grado, Social Studies, Advisory.

**Si por conflicto NO puedes asignarlo:** el evaluador cuenta como violación. Mejor sacrificar electivas que required.

### H5 — Master fijo (CRÍTICO)

**Regla:** las columnas `SectionID`, `Slots`, `TeacherID`, `RoomID` del output deben coincidir EXACTAMENTE con `sections.csv`.

- No inventes SectionIDs nuevos
- No modifiques los slots de una sección existente
- No cambies el profesor o aula

**Ejemplo de violación:** `sections.csv` dice `A0901.1` tiene slots `A5;C3;E1`. El output dice `A0901.1` tiene slots `B2;D4;E1`. **Inválido.**

**Implementación:** después de decidir a qué sección va el estudiante, COPIA literalmente las 4 columnas de `sections.csv`. No las calcules.

### H6 — Solo cursos solicitados

**Regla:** un estudiante solo puede aparecer en secciones de cursos que están en su `course_requests`.

No "rellenes" slots libres con cursos no pedidos.

### H7 — Una sección por curso por estudiante

**Regla:** si un alumno pide 8 cursos, su output tiene ≤ 8 rows. Cada `CourseID` aparece ≤ 1 vez por StudentID.

### H8 — Term pairs (excepción a H1)

**Regla:** dos cursos con `relationship_code='Term'` en `course_relationships.csv` pueden compartir slot.

**Hoy:** 1 par. `I1213 ↔ I1212` (AP Macroeconomics ↔ AP Microeconomics). Comparten slot porque corren en semestres distintos (S1 vs S2).

**Suffix match:** si un alumno toma AMBOS:
- ✅ `I1212.1` con `I1213.1` (mismo sufijo)
- ❌ `I1212.1` con `I1213.2` (sufijos diferentes — prohibido)

Si solo toma uno, ningún constraint adicional.

### H9 — Simultaneous pairs

**Regla:** dos cursos con `relationship_code='Simultaneous'` están en el MISMO slot intencionalmente. Un estudiante NO toma ambos (sería double-booking real).

**Hoy:** 6 pares HS:
- `OC1313 ↔ I1215`
- `OC1307 ↔ OC1311`
- `OC1306 ↔ OC1312`
- `G1204 ↔ G0902`
- `G1205 ↔ G0902`
- `G1206 ↔ G0902`

**Implicación:** si tu lógica detecta "dos cursos en mismo slot" como problema, EXCLUYE estos pares — no es problema.

### H10 — Teacher Assistants

**Tabla:** `teacher_assistants.csv`
**Hoy:** 27 TAs en HS.

**Regla:** si alumno X está en `teacher_assistants.csv` con `target_course_name="AP Drawing"` y `target_teacher_id=46`, entonces SU asignación a AP Drawing DEBE ser la sección impartida por `teacher_id=46` — no otra sección de AP Drawing con otro profesor.

**Implementación:**
```python
for ta in teacher_assistants.csv:
    if ta.student in assigned:
        course_matches = [c for c in courses if c.name == ta.target_course_name]
        for cid, sec in assigned[ta.student]:
            if cid in course_matches:
                if sections[sec].teacher_id != ta.target_teacher_id:
                    VIOLATION
```

### H11 — Teacher avoid

**Tabla:** `teacher_avoid.csv` (11 reglas HS)

**Regla:** alumno X con `teacher_id=T` en la tabla NO puede ser asignado a NINGUNA sección con `teacher_id=T`.

### H12 — Student pair constraints

**Tabla:** `student_pair_constraints.csv` (161 pares HS)

**Relations:**
- `separate` — los dos estudiantes NO comparten sección en NINGÚN curso
- `together` — si ambos toman el mismo curso, DEBEN ir a la misma sección

**Ejemplo separate violado:** alumnos 28102 y 28103 marcados `separate`, ambos asignados a `H0904.1` (English 9).

**Ejemplo together violado:** alumnos 27001 y 27002 marcados `together`, ambos toman AP Bio pero uno está en `OA1304.1` y el otro en `OA1304.2`.

### H13 — AP no se sustituye

**Regla:** un curso AP no se reemplaza por uno regular. Aplica si tu algoritmo intenta sustituir cursos que no caben. Si tú solo asignas requests, no aplica.

### H14 — = H7 (una sección por curso)

---

## SOFT CONSTRAINTS

### S1 — Cobertura

Maximiza `(student, course)` pairs asignados. Métrica primaria del ranking.

### S2 — Balance

Diferencia ≤ 3 entre la sección más llena y la más vacía del mismo curso. Stddev del enrollment.

### S3 — Weighted placement

```python
PRIORITY = {'A':10000, 'B':1000, 'C':100, 'D':10, 'F':1}  # estudiante: A=máxima
FLEX     = {'A':1, 'B':2, 'C':5, 'D':50, 'F':500}         # curso: A=más flexible (peso BAJO)
```

**Flexibilidad invertida:** F (rígido, AP, required) tiene peso 500 → resolver SÍ o SÍ. A (electiva sustituible) tiene peso 1 → OK perderlo.

`weight = PRIORITY[student.prio] * FLEX[course_flex_at(course, grade)]`

Rango: 1 ↔ 5,000,000. Cuando hay competencia por un cupo, prioriza el peso más alto.

### S4 — Co-planning preferences

`co_planning_options.csv` — informativo. Si el Master ya asignó profesores que coinciden con preferencias del file, mejor.

### S5 — E3 reservado

Slot `E3` reservado para Advisory en HS. Tu output no debe poner secciones académicas en E3. (El Master ya respeta esto; solo no rompas.)

---

## Casos comunes

### Caso A: Un curso requerido no cabe en ningún slot del alumno

**Escenario:** alumno tiene 22 slots ocupados, 3 libres. El curso `English 11` requerido tiene secciones en slots que él ya tiene ocupados.

**Decisión:** omite la fila para `English 11`. El evaluador lo marca como H4 violation, pero es preferible a violar H1 (double-booking) o H5 (modificar Master).

### Caso B: TA cuya target section está llena

**Escenario:** alumno TA debe ir a `OC1314.1` (AP Drawing) pero esa sección ya tiene 25/25.

**Decisión:** no asignes ese curso al alumno. H10 dice "SI lo asignas debe ser esa sección" — no obliga a asignar si no cabe. Es preferible que no tome el curso a que viole H10.

### Caso C: Dos `separate` pairs toman el mismo curso con 1 sección

**Escenario:** alumnos A y B marcados `separate` ambos toman `H0904` que solo tiene 1 sección.

**Decisión:** asigna al que tenga mayor prioridad (S3). Al otro, deja sin asignar para ese curso. Violar H12 separate es serio; H1 cobertura es soft.

### Caso D: Alumno con `teacher_avoid` que cubre TODOS los profesores de un curso requerido

**Escenario:** alumno tiene avoid para teacher 5 y 7, y el curso `H1001` (English 10, required) solo tiene 2 secciones — una con teacher 5 y otra con teacher 7.

**Decisión:** omite. Es un conflicto irresoluble en los datos. Marca H4 como violation (curso requerido sin asignar). No violes H11.

### Caso E: Student pair `together` pero solo uno tiene el curso en su request

**Escenario:** alumnos 27001 y 27002 marcados `together`. 27001 tiene `H1206` en su request, 27002 no.

**Decisión:** H12 together solo aplica si AMBOS toman el curso. Asigna a 27001 a la sección que quieras; 27002 no toma ese curso (no está en su request).

---

## Decisión jerárquica recomendada

Cuando tengas que sacrificar algo, jerarquía sugerida:

1. **Nunca violes H5 (Master) ni H1 (double-booking).** Son irrecuperables.
2. **Nunca violes H3 (grade) ni H6 (request).** Académicamente inválido.
3. **Prefiere violar H4 (required) antes que H11 (avoid) o H12 (pair).** Los avoid/pair son decisiones del consejero; los required son interpretables.
4. **Cobertura (S1) cede ante todo.** Mejor un alumno con 6/7 cursos legítimos que con 7/7 pero un curso ilegal.
