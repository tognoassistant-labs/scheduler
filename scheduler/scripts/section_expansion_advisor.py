#!/usr/bin/env python3
"""Section-expansion advisor — translates the unmet list into a ranked
operational ask for the school admin team.

For each course with unmet students, computes:
  - n_unmet:           how many students missed this course
  - currently:         existing sections + their teachers + enrolled/cap
  - bottleneck_type:   capacity-bound | grid-bound | both
  - recovery_estimate: upper bound on students recovered by adding 1 section
  - free_slot_pattern: which (day, block) slots most unmet students have free
  - teacher_options:   existing qualified teachers + "needs new hire?" flag

Output:
  - markdown table sorted by recovery_estimate descending
  - per-course detail block with the slot analysis

Usage:
    python scheduler/scripts/section_expansion_advisor.py \
        scheduler/data/_client_bundle_v4/HS_2026-2027_real

The path argument should point to a bundle subdir that contains
input_data/ + horario_estudiantes/ + powerschool_upload/.

Output goes to stdout (pipe to a file for sharing with the school).
"""
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path


def load_bundle(bundle_dir: Path):
    """Load the four CSVs we need from a bundle."""
    def _csv(rel: str) -> list[dict]:
        with (bundle_dir / rel).open() as f:
            return list(csv.DictReader(f))
    return {
        "courses":   _csv("input_data/courses.csv"),
        "sections":  _csv("input_data/sections.csv"),
        "teachers":  _csv("input_data/teachers.csv"),
        "students":  _csv("input_data/students.csv"),
        "requests":  _csv("input_data/course_requests.csv"),
        "schedules": _csv("horario_estudiantes/student_schedules.csv"),
        "unmet":     _csv("horario_estudiantes/unmet_requests.csv"),
        "enrollment": _csv("horario_estudiantes/sections_with_enrollment.csv"),
        "master":    _csv("powerschool_upload/ps_master_schedule.csv"),
    }


def analyze(bundle_dir: Path) -> str:
    """Return a Markdown report ranking courses by section-expansion value."""
    b = load_bundle(bundle_dir)

    # Course lookup
    course_by_id = {c["course_id"]: c for c in b["courses"]}

    # Per-section: enrolled + slots from master
    enrolled_by_sec: dict[str, int] = {}
    max_size_by_sec: dict[str, int] = {}
    for s in b["enrollment"]:
        enrolled_by_sec[s["section_id"]] = int(s["enrolled"])
        max_size_by_sec[s["section_id"]] = int(s["max_size"])

    slots_by_sec: dict[str, set[tuple[str, int]]] = defaultdict(set)
    for r in b["master"]:
        slots_by_sec[r["Section_ID_Internal"]].add((r["Day"], int(r["Block"])))

    # Sections per course
    sections_by_course: dict[str, list[str]] = defaultdict(list)
    teacher_by_section: dict[str, str] = {}
    for s in b["sections"]:
        sections_by_course[s["course_id"]].append(s["section_id"])
        teacher_by_section[s["section_id"]] = s["teacher_id"]

    # Teacher names
    teacher_name = {t["teacher_id"]: t["name"] for t in b["teachers"]}

    # Qualified teachers per course
    qualified: dict[str, set[str]] = defaultdict(set)
    for t in b["teachers"]:
        for cid in (t.get("qualified_course_ids") or "").split("|"):
            if cid:
                qualified[cid].add(t["teacher_id"])

    # Per-student busy slots (so we can find what's free for each unmet student)
    busy_by_student: dict[str, set[tuple[str, int]]] = defaultdict(set)
    for r in b["schedules"]:
        sids = (r["section_ids"] or "").split("|")
        for sid in sids:
            for slot in slots_by_sec.get(sid, set()):
                busy_by_student[r["student_id"]].add(slot)

    # Group unmet by course
    unmet_by_course: dict[str, list[str]] = defaultdict(list)
    for r in b["unmet"]:
        unmet_by_course[r["course_id"]].append(r["student_id"])

    # ---- Compute metrics per course ----
    rows = []
    for cid, unmet_students in unmet_by_course.items():
        course = course_by_id.get(cid, {"name": "??", "max_size": "25"})
        course_name = course.get("name", "??")
        max_size = int(course.get("max_size", "25") or 25)
        secs = sections_by_course.get(cid, [])
        total_cap = sum(max_size_by_sec.get(s, max_size) for s in secs)
        total_enr = sum(enrolled_by_sec.get(s, 0) for s in secs)
        free_seats = total_cap - total_enr

        # Demand: requests for this course
        demand = sum(1 for r in b["requests"] if r["course_id"] == cid)

        # Bottleneck classification
        if free_seats <= 0:
            bottleneck = "capacity"  # all sections full
        elif free_seats >= len(unmet_students):
            bottleneck = "grid"  # plenty of seats but slots conflict
        else:
            bottleneck = "both"

        # Find slots common to many unmet students (good candidates for new section)
        # For each (day, block) slot, count how many unmet students are FREE there.
        slot_freedom: Counter[tuple[str, int]] = Counter()
        ALL_SLOTS = [(d, b_) for d in "ABCDE" for b_ in range(1, 6)]
        for stu in unmet_students:
            busy = busy_by_student.get(stu, set())
            for slot in ALL_SLOTS:
                if slot not in busy and slot != ("E", 3):  # E3 reserved for advisory
                    slot_freedom[slot] += 1

        # A new section needs 3 (day, block) slots all in the same scheme.
        # Approximation: pick top 3 slots by freedom, see how many students are
        # free in ALL three. This is a lower bound on real recovery.
        top3 = [s for s, _ in slot_freedom.most_common(3)]
        if len(top3) >= 3:
            est_recovery = sum(1 for stu in unmet_students
                               if all(slot not in busy_by_student.get(stu, set())
                                      for slot in top3))
            est_recovery = min(est_recovery, max_size)
        else:
            est_recovery = 0

        # Existing teachers of this course + their current load
        existing_teachers = list({teacher_by_section[s] for s in secs})
        teacher_load = Counter(teacher_by_section.values())
        teacher_situation_lines = []
        for tid in existing_teachers:
            t_name = teacher_name.get(tid, tid)
            n_sec = teacher_load.get(tid, 0)
            teacher_situation_lines.append(f"{t_name}: {n_sec} sec totales")
        teacher_situation = " · ".join(teacher_situation_lines) or "(sin profesor asignado)"

        rows.append({
            "course_id": cid,
            "name": course_name,
            "n_unmet": len(unmet_students),
            "currently": f"{len(secs)} sec / {total_enr}/{total_cap} cap",
            "demand": demand,
            "bottleneck": bottleneck,
            "free_seats_today": free_seats,
            "est_recovery_with_new_section": est_recovery,
            "best_slot_pattern": ", ".join(f"{d}{b}" for d, b in top3) if top3 else "—",
            "teacher_options": teacher_situation,
            "max_size": max_size,
        })

    # Sort by est_recovery descending — most rentable first
    rows.sort(key=lambda r: -r["est_recovery_with_new_section"])

    # ---- Build markdown report ----
    out = []
    out.append("# Section-expansion advisor — propuesta para admin")
    out.append("")
    out.append(f"Bundle: `{bundle_dir}`")
    out.append(f"Total cursos con unmet: **{len(rows)}**")
    out.append(f"Total estudiantes afectados (cupos): **{sum(r['n_unmet'] for r in rows)}**")
    out.append("")
    out.append("## Ranking — recuperación estimada por nueva sección")
    out.append("")
    out.append("La columna **Recuperaría hasta** estima cuántos de los `n_unmet` "
               "podrían entrar si se abre 1 sección adicional en los slots "
               "sugeridos (limite superior; recovery real depende de quién "
               "dicta y dónde la pone el motor en la próxima corrida).")
    out.append("")
    out.append("| Curso | Nombre | Unmet | Cupos hoy | Tipo | Recuperaría hasta | Slot sugerido | Profe(s) actual(es) |")
    out.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        if r["est_recovery_with_new_section"] == 0 and r["n_unmet"] == 0:
            continue
        out.append(
            f"| {r['course_id']} | {r['name']} | {r['n_unmet']} | "
            f"{r['currently']} | {r['bottleneck']} | "
            f"**{r['est_recovery_with_new_section']}** | {r['best_slot_pattern']} | "
            f"{r['teacher_options']} |"
        )

    # Detail per high-impact course
    out.append("")
    out.append("## Detalle de los top 5")
    out.append("")
    for r in rows[:5]:
        out.append(f"### {r['course_id']} — {r['name']}")
        out.append(f"- **{r['n_unmet']} estudiantes** sin asignar")
        out.append(f"- Hoy: {r['currently']} (demanda total: {r['demand']})")
        out.append(f"- Tipo de cuello: **{r['bottleneck']}**")
        if r["bottleneck"] == "capacity":
            out.append(f"  - No hay cupos libres. Cualquier sección extra recupera linealmente.")
        elif r["bottleneck"] == "grid":
            out.append(f"  - Hay {r['free_seats_today']} cupos libres pero los slots chocan con otros required de los unmet.")
        else:
            out.append(f"  - {r['free_seats_today']} cupos libres + algunos casos donde los slots chocan.")
        out.append(f"- **Si se abre 1 sección extra de tamaño ≤{r['max_size']}**, "
                   f"recuperaría hasta **{r['est_recovery_with_new_section']}** estudiantes.")
        out.append(f"- Slots sugeridos para esa sección: `{r['best_slot_pattern']}` (donde más unmet están libres simultáneamente).")
        out.append(f"- Profesor(es) actual(es) del curso: {r['teacher_options']}")
        out.append(f"- Decisión admin: ¿alguno de ellos puede tomar 1 sección más, o requiere nuevo profesor?")
        out.append("")

    # Aggregate suggestion
    total_recovery = sum(r["est_recovery_with_new_section"] for r in rows[:5])
    total_unmet = sum(r["n_unmet"] for r in rows)
    out.append("## Resumen ejecutivo")
    out.append("")
    out.append(f"- Si se aprueban las **5 secciones del top**, recuperación estimada: **~{total_recovery} estudiantes**.")
    out.append(f"- Esto subiría la cobertura de required del actual {round(100*(4636-total_unmet)/4636,1)}% "
               f"hacia ~{round(100*(4636-total_unmet+total_recovery)/4636,1)}%.")
    out.append("- Decisión administrativa requerida: profesor + aula + slots por cada nueva sección.")
    out.append("")
    out.append("**Nota:** la recuperación es un estimado superior. La cifra real depende de "
               "qué profesor se asigne, dónde caigan los slots, y de cómo el motor re-acomode "
               "los demás cursos en la siguiente corrida.")

    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <bundle_dir>")
        sys.exit(1)
    bundle = Path(sys.argv[1])
    if not bundle.exists():
        print(f"Bundle dir not found: {bundle}")
        sys.exit(1)
    print(analyze(bundle))
