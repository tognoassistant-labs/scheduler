# Swarm experiment v2 — HS schedule assignment

**Segunda iteración.** La primera (folder `swarm_handoff_2026-05-30/`) falló: ambos agentes (OR-Tools, Rust) entregaron outputs con cientos de violaciones de hard constraints.

Esta versión incluye: lecciones del round 1, schema explícito, validador automático, baseline conocida para comparar.

**Empieza por `HANDOFF.md`.** Luego `context/round_1_lessons.md` (errores anteriores).

## Estructura

```
swarm_handoff_v2_2026-05-30/
├── HANDOFF.md                          ← Spec del problema + schema exacto
├── README.md                           ← Este archivo
├── validate.py                         ← Pre-flight obligatorio
├── context/
│   ├── round_1_lessons.md              ← Qué falló antes
│   ├── known_impossible_cases.md       ← 12 casos donde omitir es legítimo (H4)
│   ├── constraints.md                  ← Detalle de hard + soft con ejemplos
│   └── glossary.md                     ← Términos del dominio
└── data/                               ← 15 CSVs con datos reales
    │  CORE
    ├── students.csv (509)
    ├── courses.csv (74)
    ├── sections.csv (248)              ← Master FIJO (no modificar)
    ├── course_requests.csv (4,610)
    ├── teachers.csv (48)
    ├── rooms.csv (38)
    │  CONSTRAINTS
    ├── course_relationships.csv (7)    ← Term + Simultaneous pairs
    ├── teacher_assistants.csv (27)
    ├── teacher_avoid.csv (11)
    ├── student_pair_constraints.csv (161)
    ├── system_rules.csv (10)
    ├── student_priorities.csv (509)
    ├── course_flexibility.csv (132)
    ├── co_planning_options.csv (40)
    └── course_equivalencies.csv (0)
```

## Tarea (resumen)

Asignar 509 estudiantes HS a las 248 secciones existentes respetando 14 hard constraints + 5 soft. Entregable: `student_schedules_friendly.csv` con **12 columnas exactas**.

## Cómo trabajar

1. Lee `HANDOFF.md` completo (especialmente el schema y los 14 hard constraints)
2. Lee `context/round_1_lessons.md` (qué falló antes — no lo repitas)
3. Lee `context/constraints.md` (detalle de cada constraint con casos)
4. Implementa tu solución
5. **OBLIGATORIO:** corre `python validate.py student_schedules_friendly.csv` ANTES de entregar
6. Si reporta ❌, **corrige y re-valida** — no entregues con violaciones
7. Entrega solo el CSV

## Baseline a igualar

| Métrica | Nuestra app (con TODOS los constraints respetados) |
|---|---|
| Students complete | 497/509 = **97.64%** |
| Requests satisfied | 4,597/4,610 = **99.72%** |
| Hard violations | **0** |

**Superar 97.64% con 0 violaciones es matemáticamente posible solo si encuentras asignaciones más eficientes que las nuestras. Si tu cobertura es muy superior pero con violaciones, NO estás mejorando — estás haciendo trampa.**

## Filosofía

No buscamos un solver más rápido. Buscamos uno **CORRECTO**. Una solución 95% correcta legítima vale más que 98% que viola reglas.
