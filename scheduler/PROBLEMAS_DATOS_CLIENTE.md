# Problemas de calidad y entrega de datos del cliente

**Última actualización:** 2026-04-28 (cierre de día)
**Versiones bundle afectadas:** v3, v4, v4.1, v4.2
**Impacto acumulado:** ~5 días perdidos en limpieza, diagnóstico y rondas de aclaración con el cliente.

Este registro existe para que el cliente entienda dónde se pierde tiempo y pueda decidir si corregir el origen (PowerSchool / hojas oficiales) o si aceptamos los workarounds actuales.

---

## A. Problemas estructurales en los datos entregados

### 1. Cursos semestrales sin marcador de pareja

**Archivos:** `columbus_official_2026-2027.xlsx` hoja `teacher_assignments` + `course_relationships.xlsx`

**Problema:** AP Microeconomics (I1213, S1) y AP Macroeconomics (I1212, S2) son el mismo bloque pero contenido distinto por semestre. Sin la información de relación, el motor los trataba como 8 secciones simultáneas → master INFEASIBLE.

**Tiempo perdido:** 1.5 días (diagnóstico + workaround + nuevo bug en partitioning).

**Estado:** Workaround v4.1/v4.2 = omitir secciones S1/S2. Modelo properly preparado en v4.2 pero defer a v4.3 porque el global scheme-balance constraint hace INFEASIBLE en Ortegon's home_room.

**Causa raíz:** la información de la relación (Block/Term) llegó **3 días después** del archivo canónico inicial. Si el archivo canónico hubiera traído `course_relationships` desde el inicio, no habría habido bug.

---

### 2. Cursos multi-nivel (Spanish FL, Drawings, Sculptures, AP Art) sin marcador

**Archivos:** mismo

**Problema:** una profesora dicta Spanish 9/10/11/12 FL en EL MISMO BLOQUE simultáneamente (multi-level class). PS los lista como 4 sections separadas. Sin la info de relación "Simultaneous", el motor sumaba 4 al pigeonhole de Clara, dando 9 secciones (infeasible) cuando en realidad son 5 físicas.

**Tiempo perdido:** 1 día (diagnóstico de "sobrecarga" + override max_consec=5 + reversión).

**Estado:** ✅ **Resuelto en v4.2** una vez que llegó el archivo `course_relationships.xlsx`. Clara: 9→5 secciones, Sofia: 8→6.

**Causa raíz:** mismo timing — la relación "Simultaneous" no estaba en el archivo canónico inicial. Habría ahorrado 1 día completo de debug.

---

### 3. Coplanning sheet existía pero no la mencionaron

**Archivo:** `rfi_1._STUDENTS_PER_COURSE_2026-2027.xlsx` hoja `CO PLANNING INFO` (13 grupos prioritarios + más en orden de importancia)

**Problema:** este archivo lo recibimos al **inicio del proyecto** (semanas atrás). La hoja `CO PLANNING INFO` siempre estuvo ahí. El cliente no la mencionó hasta 2026-04-28.

**Tiempo perdido:** preguntas múltiples sobre "regla de coplanificación no implementada" en el doc Reglas Horarios — 0.5 día.

**Estado:** Pendiente para v4.3 (archivo ya local, falta solo implementar el constraint).

**Causa raíz:** falta de mapeo entre las "reglas" del documento de bloqueadores y los datos disponibles. El cliente referenció un Drive ID nuevo (`1JfxXR0...`) pero el archivo ya estaba en `reference/`.

---

### 4. Estudiante 29096 con 10 cursos obligatorios cuando el techo es 8

**Archivo:** hoja `requests` del canónico

**Problema:** un estudiante tiene 10 cursos requested marcados `is_required=True`. Pero el grid HS solo tiene 9 slots académicos por estudiante, y el cliente confirmó que **el target es 8** (excepto AP Economics que cuenta 9 por compartir slot).

**Tiempo perdido:** 1 día (implementación de soft penalty en student_solver para no fallar INFEASIBLE).

**Estado:** Workaround = soft penalty con coverage 94.6-94.8%. **El cliente debe revisar este estudiante** y bajar requests a ≤9.

**Causa raíz:** error de captura en course requests. Problema de calidad de datos del cliente, no nuestro.

---

### 5. Profesores con carga académica pigeonhole-imposible

**Archivo:** `teacher_assignments`

**Problema:** Sofia Arcila, Gloria Vélez, Clara Martínez aparecen con ≥7 secciones académicas, pigeonhole-infeasible al cap global de 4 consecutivos.

**Estado:** En v4.2 con Simultaneous merge, Sofia bajó a 6 y Clara a 5 — ya no necesitan override. Gloria sigue con 7 (no tiene cursos en relaciones Simul). El cliente confirmó: "verificará con la escuela, si esta condición se da que haga el override solo si verdaderamente le aplica".

**Causa raíz:** parcialmente resuelto por la info de relaciones. Para Gloria queda pendiente decisión operativa.

---

### 6. Profesores con 5 bloques seguidos en horario actual (reportado por cliente)

**Reportado por cliente:** Castañeda con 5 bloques en Día C.

**Problema:** el horario actual de Columbus **ya viola HC3=4 consecutivos**. Si bajamos el cap global a 5, otros profes terminan con 5+ y el cliente lo señala.

**Estado:** Cap global = 4, override per-teacher para casos pigeonhole-infeasible. Aceptado por cliente.

---

### 7. IDs como float

**Archivos heurísticos (v3 y antes):** Student IDs como `28025.0` en lugar de `28025`.

**Estado:** Resuelto con normalizador `_id_str()`.

---

### 8. Cursos en LISTADO MAESTRO sin demanda real

**Estado:** Filtrados automáticamente por el ingester. Cosmético.

---

## B. Problemas en la entrega/coordinación de archivos

Esta categoría es nueva en esta versión. Documenta el patrón de "archivos críticos llegan tarde", que ha sido el mayor consumidor de tiempo.

### B1. Spec de PowerSchool import llegó después del v3

**Cuándo:** 2026-04-28
**Archivo:** Google Sheet con spec oficial de columnas (`Section_Number`, `Att_Mode_Code`, `Attendance_Type_Code`, `GradebookType`, `TermID` formato real)

**Impacto:** el bundle v3 se entregó al cliente con **slugs internos** y formato incorrecto. v4.1 tuvo que reescribir el exporter completo para cumplir la spec.

**Tiempo:** 0.5 día.

---

### B2. course_relationships.xlsx llegó 4 días después del canónico

**Cuándo:** 2026-04-28
**Archivo:** Google Sheet con 7 relaciones (6 Simultaneous + 1 Term)

**Impacto:** ver problemas 1 y 2 arriba. ~2 días de debug innecesarios diagnosticando "sobrecargas" y "secciones imposibles" que en realidad eran multi-level / semester-paired.

---

### B3. TermID format no especificado, hubo que preguntar

**Cuándo:** 2026-04-28
**Pregunta:** ¿`TermID=3600` es año, semester o quarter? ¿Existen `3601`/`3602`?
**Respuesta:** 3600 año, 3601 S1, 3602 S2.

**Impacto:** v4.1 generado con TermID=3600 para todo. v4.2/v4.3 podrá modelar Term properly con esta info.

---

### B4. Archivo de Juan ("cursos que cada estudiante debe tener") llegó tarde

**Cuándo:** 2026-04-28 (mismo día)
**Sheet ID:** `1k_6BUOOAL2UEOjjfznYXVw9LY5NXFlABu8KxPFkr3h0`

**Estado:** Pendiente revisar contenido (60kb, requiere lectura por chunks). Probable que sea la fuente autoritativa de demanda y reemplace lo que tenemos en `requests` del canónico.

**Impacto potencial:** si reemplaza la demanda actual, v4.3 tiene que regenerar todo desde este archivo.

---

### B5. Archivo de coplanning compartido por URL Drive sin acceso a nuestra cuenta

**Cuándo:** referenciado en doc de bloqueadores 2026-04-28
**URL:** `1JfxXR0GKoBd5p2LQM4qODor964l9ekXbBE37vF-L8dU`

**Problema:** el ID en el doc del cliente NO está compartido con nuestra cuenta Drive del MCP. `read_file_content` retorna "Requested entity was not found". Casualidad: el archivo YA estaba localmente como `rfi_1._STUDENTS_PER_COURSE_2026-2027.xlsx`.

**Impacto:** 0.25 día de búsqueda + verificación de que el archivo local tiene la hoja correcta.

---

## C. Resumen de tiempo perdido

| Categoría | Tiempo |
|---|---|
| **A — Calidad de datos** | ~3 días (problemas 1-7 originales) |
| **B — Timing de entregas** | ~2 días (B1-B5, archivos críticos llegando después de cada bundle) |
| **TOTAL ACUMULADO** | **~5 días** |

---

## D. Estado de versiones del bundle

| Versión | Fecha | Cobertura | Notas |
|---|---|---|---|
| v3 | 2026-04-26 | 92% | Slugs internos, sin canonical PS data |
| v4 | 2026-04-28 (mañana) | 94.6% | Canonical PS data + soft penalty |
| v4.1 | 2026-04-28 (mediodía) | 94.6% | PS import format compliance |
| v4.2 | 2026-04-28 (tarde) | 94.8% | Simultaneous course merge |
| **v4.3** | **pendiente** | **objetivo 97%+** | Term sections + coplanning + archivo Juan |

---

## E. Recomendaciones al cliente (orden de impacto)

1. **(Bloqueante para 100%)** Revisar y corregir estudiantes con >9 cursos requested. El estudiante 29096 es el caso más visible — probable que haya más. Sin esto, cobertura tope ~95-97%.

2. **(Bloqueante para v4.3)** Confirmar/corregir relaciones Term. AP Micro/Macro está documentado pero podría haber otros pares semestrales no listados en `course_relationships.xlsx`.

3. **(Para Track B)** Decidir política de carga docente. ¿Reducir Sofía/Gloria/Clara a 6 sections cada una, o mantener override?

4. **(Coordinación)** Cuando se entreguen archivos críticos (relaciones, demanda, spec), entregarlos **en un solo paquete** en lugar de goteo de 3-4 días. El goteo es la causa principal de los 2 días perdidos en "B".

5. **(Pre-demo 1-mayo)** Decidir si en demo se muestra v4.2 (94.8%, semester courses omitidas) o se espera a v4.3 (semester + coplanning).
