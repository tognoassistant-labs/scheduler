"""Built-in rule registrations.

Every field of `HardConstraints` and `SoftConstraintWeights` that the
school may want to toggle or tune from the UI is registered here. Rules
the user cannot reasonably change (advisory_day, advisory_block — both
fixed at E3 by district policy) are intentionally omitted.

Stable IDs (R_*) are forever — once persisted in a rule_config we cannot
rename them without breaking historical runs. Adding a new rule = adding
one entry below; renaming an existing rule = adding a new ID and leaving
the old one in place (or providing a migration).

Defaults must mirror models.py exactly. Tests enforce this.
"""
from __future__ import annotations

from .registry import Rule, rule

# ---------------------------------------------------------------------------
# HARD constraints — booleans (toggles)
# ---------------------------------------------------------------------------

rule(Rule(
    id="R_enforce_separations",
    kind="hard",
    label="Separaciones obligatorias",
    description="Los pares de estudiantes en behavior.csv (separations) NUNCA "
                "comparten sección. Off → penalización suave vía separation_violation.",
    field_path="hard.enforce_separations",
    value_type="bool",
    default=True,
    category="behavior",
))

rule(Rule(
    id="R_enforce_restricted_teachers",
    kind="hard",
    label="Teachers restringidos por estudiante",
    description="Los estudiantes nunca son asignados a teachers en su lista "
                "restricted_teacher_ids.",
    field_path="hard.enforce_restricted_teachers",
    value_type="bool",
    default=True,
    category="behavior",
))

rule(Rule(
    id="R_enforce_coplanning_groups",
    kind="hard",
    label="Co-planning de departamentos",
    description="Cada grupo en coplanning_groups debe compartir al menos un "
                "scheme libre. Costo: ~50 unmet en datos reales de Columbus.",
    field_path="hard.enforce_coplanning_groups",
    value_type="bool",
    default=True,
    category="teachers",
))

# ---------------------------------------------------------------------------
# HARD constraints — integer caps (numeric inputs)
# ---------------------------------------------------------------------------

rule(Rule(
    id="R_max_class_size",
    kind="hard",
    label="Tamaño máximo de clase",
    description="Inscritos por sección ≤ este valor (excepto AP Research).",
    field_path="hard.max_class_size",
    value_type="int",
    default=25,
    min_value=15,
    max_value=40,
    category="capacity",
))

rule(Rule(
    id="R_ap_research_max_size",
    kind="hard",
    label="Tamaño máximo AP Research",
    description="Excepción de capacity para AP Research.",
    field_path="hard.ap_research_max_size",
    value_type="int",
    default=26,
    min_value=15,
    max_value=40,
    category="capacity",
))

rule(Rule(
    id="R_max_consecutive_classes",
    kind="hard",
    label="Clases consecutivas máx por teacher",
    description="Ningún teacher dicta más de N bloques consecutivos en un día.",
    field_path="hard.max_consecutive_classes",
    value_type="int",
    default=4,
    min_value=2,
    max_value=8,
    category="teachers",
))

rule(Rule(
    id="R_max_section_spread_per_course",
    kind="hard",
    label="Spread máx entre secciones del mismo curso",
    description="max_enrollment − min_enrollment dentro del mismo curso ≤ N. "
                "Política Colegio: ideal 4, aceptable 5.",
    field_path="hard.max_section_spread_per_course",
    value_type="int",
    default=4,
    min_value=2,
    max_value=10,
    category="balance",
))

rule(Rule(
    id="R_min_sections_for_balance",
    kind="hard",
    label="Mínimo de secciones para evaluar balance",
    description="Cursos con menos secciones que esto no son sometidos al "
                "constraint de balance.",
    field_path="hard.min_sections_for_balance",
    value_type="int",
    default=2,
    min_value=1,
    max_value=5,
    category="balance",
))

# ---------------------------------------------------------------------------
# SOFT weights — multi-objective tuning
# ---------------------------------------------------------------------------

rule(Rule(
    id="R_w_balance_class_sizes",
    kind="soft",
    label="Peso: balance entre secciones",
    description="Penalización por desviación de tamaños dentro del mismo curso.",
    field_path="soft.balance_class_sizes",
    value_type="int",
    default=8,
    min_value=0,
    max_value=50,
    category="balance",
))

rule(Rule(
    id="R_w_first_choice_electives",
    kind="soft",
    label="Peso: electivas rank-1",
    description="Recompensa por cumplir cada solicitud de electiva en primera "
                "opción. Más alto → más electivas cumplidas.",
    field_path="soft.first_choice_electives",
    value_type="int",
    default=20,
    min_value=0,
    max_value=100,
    category="students",
))

rule(Rule(
    id="R_w_co_planning",
    kind="soft",
    label="Peso: co-planning suave",
    description="Bonus por agrupar departamentos. 0 = off (default). >0 puede "
                "comprimir secciones del mismo dept y dañar electivas/balance.",
    field_path="soft.co_planning",
    value_type="int",
    default=0,
    min_value=0,
    max_value=50,
    category="teachers",
))

rule(Rule(
    id="R_w_grouping_codes",
    kind="soft",
    label="Peso: grouping codes (behavior soft)",
    description="Recompensa por mantener juntos pares en behavior.groupings.",
    field_path="soft.grouping_codes",
    value_type="int",
    default=4,
    min_value=0,
    max_value=50,
    category="behavior",
))

rule(Rule(
    id="R_w_teacher_load_balance",
    kind="soft",
    label="Peso: balance de carga de teachers",
    description="Penalización por desbalance en cantidad de bloques por día "
                "del teacher.",
    field_path="soft.teacher_load_balance",
    value_type="int",
    default=5,
    min_value=0,
    max_value=50,
    category="teachers",
))

rule(Rule(
    id="R_w_teacher_preferred_courses",
    kind="soft",
    label="Peso: cursos preferidos por teacher",
    description="Bonus por asignar a un teacher cursos en su lista preferred_course_ids.",
    field_path="soft.teacher_preferred_courses",
    value_type="int",
    default=3,
    min_value=0,
    max_value=50,
    category="teachers",
))

rule(Rule(
    id="R_w_teacher_avoid_courses",
    kind="soft",
    label="Peso: cursos evitados por teacher",
    description="Penalización por asignar a un teacher cursos en su lista avoid_course_ids.",
    field_path="soft.teacher_avoid_courses",
    value_type="int",
    default=5,
    min_value=0,
    max_value=50,
    category="teachers",
))

rule(Rule(
    id="R_w_teacher_preferred_blocks",
    kind="soft",
    label="Peso: bloques preferidos por teacher",
    description="Bonus por dictar en bloques en preferred_blocks.",
    field_path="soft.teacher_preferred_blocks",
    value_type="int",
    default=2,
    min_value=0,
    max_value=50,
    category="teachers",
))

rule(Rule(
    id="R_w_teacher_avoid_blocks",
    kind="soft",
    label="Peso: bloques evitados por teacher",
    description="Penalización por dictar en bloques en avoid_blocks.",
    field_path="soft.teacher_avoid_blocks",
    value_type="int",
    default=3,
    min_value=0,
    max_value=50,
    category="teachers",
))

rule(Rule(
    id="R_w_singleton_separation",
    kind="soft",
    label="Peso: separación de cursos singleton",
    description="Empuja cursos de una sola sección a schemes distintos para "
                "reducir conflictos. Off por default.",
    field_path="soft.singleton_separation",
    value_type="int",
    default=0,
    min_value=0,
    max_value=50,
    category="balance",
))

rule(Rule(
    id="R_w_separation_violation",
    kind="soft",
    label="Peso: violación de separación (cuando hard=off)",
    description="Penalización aplicada solo cuando R_enforce_separations está "
                "off. Alto → cumple casi todas; bajo → permite romperlas.",
    field_path="soft.separation_violation",
    value_type="int",
    default=1000,
    min_value=0,
    max_value=10000,
    category="behavior",
))
