# Columbus — Bundle de horarios 2026-2027

**Generado:** 2026-04-28
**Versión:** v4 (datos canónicos PowerSchool + soft penalty para estudiantes sobreasignados)

> ✅ **IDs reales de PowerSchool**: A diferencia de v3, este bundle usa los IDs
> canónicos del archivo oficial entregado por IT (`columbus_official_2026-2027.xlsx`):
> `CourseNumber` (ej. `G0901`, `AP_CALCULUS_`), `Teacher.DCID`, `Room.DCID`, etc.
> Listo para importación directa a PowerSchool sin find-and-replace.

> ⚠️ **Cobertura no llega al 100%** — el archivo de requests del cliente contiene
> estudiantes con más cursos solicitados (10) que slots académicos disponibles en
> la semana (9). El motor usa **soft penalty** para asignar lo máximo posible
> (~93-95% cobertura) y reporta los unmet requests en el archivo
> `PROBLEMAS_DATOS_CLIENTE.md` (raíz del repo). Decisión cliente pendiente: aceptar
> cobertura parcial o reducir requests en origen.

> _English version: [00_README_FIRST_en.md](00_README_FIRST_en.md)._

---

## Estructura del paquete

```
columbus_2026-2027_bundle/
├── 00_LEEME_PRIMERO.md                 ← este archivo
├── 00_README_FIRST_en.md               ← versión en inglés
├── 01_PREGUNTAS_PARA_COLUMBUS.md       ← bloqueadores y verificaciones pendientes ⚠️
├── 01_QUESTIONS_FOR_COLUMBUS_en.md     ← versión en inglés
├── 02_KPI_REPORT.md                    ← resumen de qué KPIs alcanzamos
│
├── HS_2026-2027_real/                  ← datos reales de Columbus (510 estudiantes)
│   ├── horario_estudiantes/
│   │   └── student_schedules_friendly.csv
│   ├── powerschool_upload/
│   │   ├── ps_sections.csv
│   │   ├── ps_enrollments.csv
│   │   ├── ps_master_schedule.csv
│   │   └── ps_field_mapping.md
│   └── lms_upload/
│       └── (7 CSVs OneRoster v1.1)
│
└── MS_2026-2027_synthetic_PoC/         ← prueba de concepto (datos sintéticos)
    ├── horario_estudiantes/
    │   └── student_schedules_friendly.csv
    ├── powerschool_upload/
    │   └── (3 CSVs PS)
    └── lms_upload/
        └── (7 CSVs OneRoster)
```

## Orden de lectura recomendado

1. **Este archivo** (5 min) — entender qué es cada cosa.
2. **`01_PREGUNTAS_PARA_COLUMBUS.md`** (15 min) — **estas preguntas bloquean activamente la importación a producción**. Responderlas es el siguiente paso crítico.
3. **`02_KPI_REPORT.md`** (5 min) — resumen visual de los resultados del solver.
4. **`HS_2026-2027_real/horario_estudiantes/student_schedules_friendly.csv`** — abrir en Excel para ver cualquier horario individual.

## Lo que está en este bundle

### HS (datos reales de Columbus)

- **510 estudiantes** ubicados en grados 9-12 (129 / 128 / 132 / 121)
- **234 secciones** dictadas por 43 docentes en 38 salones
- Datos extraídos de `rfi_1._STUDENTS_PER_COURSE_2026-2027.xlsx` y `rfi_HS_Schedule_25-26.xlsx`
- Listo para subir a PowerSchool y a cualquier LMS compatible con OneRoster

### MS (prueba de concepto sintético)

- **600 estudiantes sintéticos** en grados 6-8 (200 cada uno)
- Catálogo de cursos sintético — **no son los cursos reales de Columbus MS**
- Mismo motor, misma rotación A-E (per v2 §4.2)
- **Propósito:** demostrar que el motor maneja MS estructuralmente. Para producción de MS necesitamos los xlsx reales (ver pregunta B3 en `01_PREGUNTAS_PARA_COLUMBUS.md`).

## Qué hacer ahora (orden recomendado)

### Paso 1 — Revisar las preguntas que bloquean (esta semana)
Abrir `01_PREGUNTAS_PARA_COLUMBUS.md`. Las preguntas de la sección **A** bloquean la importación a PowerSchool. Las de la sección **B** bloquean el alcance del proyecto. Cada respuesta acerca el go-live.

### Paso 2 — Revisar el horario en Excel (esta semana)
Abrir `HS_2026-2027_real/horario_estudiantes/student_schedules_friendly.csv` en Excel. Filtrar por `StudentID` para ver el horario completo de cualquier estudiante. Compartir con 1-2 coordinadores académicos para validación humana.

### Paso 3 — Probar en sandbox de PowerSchool (la próxima semana)
**Antes de importar a producción**, hacer un dry-run en sandbox con `HS_2026-2027_real/powerschool_upload/ps_sections.csv`. Esto valida que el formato de campos coincida con su instancia de PS. Si no hay sandbox, ver pregunta A8.

### Paso 4 — Importar a producción (después del sandbox)
Una vez validado el formato y confirmadas las preguntas A1-A7, los CSVs están listos para producción. La recomendación es importar en este orden:
1. `ps_sections.csv` → módulo Sections de PS
2. `ps_enrollments.csv` → módulo CC (course-section enrollments) de PS

`ps_master_schedule.csv` no se importa; es para revisión por coordinación.

## Cambios respecto a v2

- ✨ **HC4 — salón es por profesor** (regla del doc `Reglas Horarios HS` 2026-04-22). El motor ahora pinea cada profesor a su `home_room` único leído del LISTADO MAESTRO. 39/43 profesores reales reciben salón asignado; los 4 restantes (Sindy Margarita + 3 placeholders "New X Teacher") flotan por diseño. **Cero violaciones de HC4 en el solve.** Caso ejemplo: Hoyos Camilo, antes en 5 salones distintos, ahora todas sus 5 secciones en R900A.
- ✨ **Formato `Period`** ahora es `1(A)2(B)3(C)` (per IT 2026-04-26) en vez de `P01..P08`.
- ✨ **`SchoolID`**: 12000 (MS) / 13000 (HS) en vez del nombre de la escuela.
- ✨ **`TermID`**: 3600 (per IT 2026-04-26) — pendiente confirmar granularidad (year/semester/quarter).
- ✨ **Auto-relax silencioso de `max_consecutive_classes` revertido**. Ahora el ingester imprime un WARNING explícito a stderr nombrando los profesores con ≥7 secciones académicas (Sofia Arcila, Gloria Vélez, Clara Martínez en HS) y opciones de mitigación.

### Trade-offs medidos vs v2

- First-choice electives: 98.7% → **92.7%** (-6pt — costo del room pinning, sigue muy sobre target ≥80%)
- Unmet rank-1: 38 → 214 (más estudiantes en alterna; estructural por reducir flexibilidad de salones)
- Section balance dev: **3** ✅ (igual que v2, sigue dentro del target)
- Master solve: 4s → 1.2s (-2.8s; HC4 reduce el espacio de búsqueda)

## Iteración y código fuente

A partir del **28 de abril de 2026** todo el desarrollo se versiona en:

**https://github.com/tognoassistant-labs/scheduler**

Si tienen observaciones que generan re-trabajo (correcciones a la matriz de agrupaciones, cursos requeridos, salones por profesor, etc.), las aplicamos en el repo y regeneramos el bundle. El cycle time es típicamente <1 hora una vez que llegan los datos corregidos.

El repo contiene:

- `scheduler/src/scheduler/` — código fuente Python del motor (CP-SAT)
- `scheduler/tests/` — 109 tests automatizados que validan correctness de cada cambio
- `bundle_for_columbus/` — los zips entregables (v2 y v3) con sus hashes SHA256
- `docs/` — specs, decisiones internas, log de skills/lessons
- `reference/` — los xlsx originales de Columbus que usamos como input

## Soporte

Para preguntas técnicas: [punto de contacto técnico — pendiente]
Para preguntas operativas o de alcance: [pendiente]
