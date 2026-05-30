# Lecciones del experimento anterior (Round 1)

> Este archivo documenta los errores concretos que cometieron los 2 agentes del primer experimento (OR-Tools y Rust). Léelo antes de empezar para no repetirlos.

## TL;DR

Los 2 outputs fueron **descartados** por:
1. Esquema incorrecto (9 cols en lugar de 12, campos vacíos)
2. Cientos de violaciones de hard constraints
3. "Optimización" basada en ignorar reglas

Ninguno fue mejor que la solución actual del colegio, a pesar de que ambos reportaron buenos números.

---

## Resultados de los 2 agentes anteriores

| Métrica | OR-Tools agent | Rust agent | Baseline real (nuestra app) |
|---|---|---|---|
| Coverage (requests) | 99.72% | 96.92% | ~99.7% |
| Students complete | 97.64% | 75.44% | 97.64% |
| **Hard violations** | **404** | **445** | **0** |
| Schema (12 cols) | ❌ (9 cols) | ❌ (9 cols) | ✓ |

Aunque OR-Tools "igualó" nuestra cobertura, lo hizo violando 404 hard constraints. **Eso es trampa, no mejora.**

---

## Errores específicos cometidos

### Error 1: Schema incompleto (ambos)

**Esperado:** 12 columnas exactas en orden:
```
StudentID,StudentName,Grade,CourseID,CourseName,SectionID,Period,Slots,TeacherID,TeacherName,RoomID,RoomName
```

**Lo que entregaron:** 9 columnas, omitieron `Period`, `RoomID`, `RoomName`. Además dejaron `StudentName` y `TeacherName` vacíos en TODAS las filas.

**Cómo evitarlo:** lookup `student_name` desde `students.csv`, `teacher_name` desde `teachers.csv`, `room_name` desde `rooms.csv`. Es un simple join.

### Error 2: Inventar/modificar Master (H5 violations)

**OR-Tools:** 24 secciones con slots/teacher/room distintos a los de `sections.csv`.
**Rust:** 17 con slots distintos + **41 SectionIDs que NO EXISTEN en sections.csv** (alucinación pura).

**Ejemplo:** el agente "inventó" que `A0901.1` ocupaba slots `B2;D4;E1` cuando en `sections.csv` claramente dice `A5;C3;E1`.

**Cómo evitarlo:** los campos `SectionID`, `Slots`, `TeacherID`, `RoomID` se COPIAN desde `sections.csv` literalmente. No los calcules. No los optimices. No los modifiques.

### Error 3: Violar grade filter masivamente (H3)

**OR-Tools:** 298 violaciones. **Rust:** 271 violaciones.

**Ejemplo:** asignaron un G9 a un curso cuyo `grade_levels="11,12"` — académicamente imposible. El estudiante de 14 años no toma AP Calculus de G12.

**Cómo evitarlo:** antes de asignar (student, section), valida que `student.grade ∈ courses[section.course_id].grade_levels`. La columna `grade_levels` es CSV: `"11,12"` significa solo G11 y G12 son válidos.

### Error 4: Double-booking (H1)

**OR-Tools:** 63 estudiantes con clases simultáneas. **Rust:** 54.

**Ejemplo:** alumno asignado a sección A (slots `A2;B5;D3`) Y a sección B (slots `A2;C1;E4`). Ambas en `A2` → físicamente imposible.

**Cómo evitarlo:** lleva un set de slots ocupados por estudiante. Antes de asignar una sección S, verifica que `set(S.slots) ∩ student.busy_slots == ∅`. Solo excepción: Term pairs (H8 — solo I1212↔I1213).

### Error 5: Teacher avoid violado (H11)

**OR-Tools:** 6 violaciones. **Rust:** 7.

**Ejemplo:** alumno `28102` aparece en `teacher_avoid.csv` con `teacher_id=8`. El agente lo asignó a una sección con `teacher_id=8`.

**Cómo evitarlo:** carga `teacher_avoid.csv` como `dict[student_id → set(forbidden_teacher_ids)]`. Antes de asignar, valida.

### Error 6: Required courses faltantes (H4)

**OR-Tools:** 10. **Rust:** 52.

**Ejemplo:** alumno tiene `English 11` con `is_required=True` en su request, pero el output no lo incluye.

**Cómo evitarlo:** asigna PRIMERO los required courses (mayor prioridad). Si tienes que dejar algo fuera por conflicto, deja electivas — nunca required.

---

## Patrones de pensamiento incorrectos

### Patrón anti-1: "Voy a maximizar cobertura"

Cobertura es UNA métrica de las muchas. Maximizarla solo es válido SUJETO A los hard constraints. Si tu algoritmo asigna sin chequear grade_levels, double-booking, etc., logra "alta cobertura" pero el output es ilegal.

**El objetivo correcto:** maximizar cobertura **sujeto a** cero violaciones de hard.

### Patrón anti-2: "Voy a re-optimizar los slots"

El Master está cerrado por una razón: profesores, aulas y horarios fueron decisiones humanas previas. No los cambies. **No corras un Master de nuevo.** Solo asigna estudiantes a las secciones existentes.

### Patrón anti-3: "El CSV de output es informativo"

No. El CSV de output tiene un esquema exacto que se va a parsear automáticamente. **3 columnas faltantes ya es razón para descartar.** Y los nombres vacíos hacen el CSV inservible para el equipo del colegio que lo va a leer.

### Patrón anti-4: "Si no encuentro forma de asignar, lo dejo fuera silenciosamente"

OK, eso es válido SI realmente no hay forma. Pero si hay forma (cupo + slot libre + grade OK + sin teacher_avoid + etc.), DEBES asignar. La omisión silenciosa empeora la métrica de cobertura.

---

## Pre-flight: lo que tu solución debe pasar

Antes de entregar, corre `validate.py`:

```bash
python validate.py student_schedules_friendly.csv
```

El script debe imprimir:
```
✅ Schema: 12 cols correctas
✅ H1 double-booking: 0 violations
✅ H2 capacity: 0 violations
✅ H3 grade filter: 0 violations
✅ H4 required: 0 missing
✅ H5 Master fixed: 0 mismatches
✅ H6 invalid request: 0
✅ H7 duplicate course: 0
✅ H10 TA wrong teacher: 0
✅ H11 teacher_avoid: 0
✅ H12 separate/together: 0
Coverage: XX/4610 = XX.X%
Students complete: XX/509 = XX.X%
```

Si CUALQUIER linea es ❌, **NO entregues**. Corrige primero.

---

## Filosofía del experimento (recordatorio)

No estamos pidiendo el mejor solver del mundo. Estamos pidiendo **un solver que respete las reglas del colegio**. Una solución 95% correcta legítima vale infinitamente más que una 98% que viola reglas — porque la 98% se descarta entera por ser inadmisible.

Tu output reemplaza a la asignación humana de un consejero académico. Si tu output mete a un G9 en AP Calculus, el consejero te va a regresar el archivo y a perder credibilidad. Tu output debe ser **aceptable como producción**, no solo como benchmark.
