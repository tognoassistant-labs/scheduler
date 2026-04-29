"""End-to-end CLI for the Columbus scheduling engine.

Subcommands:
  generate-sample      Generate Grade-12 sample data CSVs (synthetic HS)
  generate-sample-ms   Generate full MS sample data CSVs (synthetic grades 6-8)
  validate             Run validation + readiness score
  solve                End-to-end: ingest → validate → solve → report → export
  scenarios            Run a preset of scenarios and compare KPIs
  import-ps            Import real Columbus xlsx files → canonical CSVs
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .io_csv import read_dataset, write_dataset
from .io_oneroster import write_oneroster
from .sample_data import make_full_ms_dataset, make_grade_12_dataset
from .validate import validate_dataset
from .master_solver import solve_master
from .student_solver import solve_students
from .reports import write_reports, compute_kpis
from .exporter import export_powerschool
from .scenarios import PRESETS, format_comparison, run_scenarios
from .ps_ingest import build_dataset_from_columbus


def cmd_generate_sample(args: argparse.Namespace) -> int:
    out = Path(args.out)
    ds = make_grade_12_dataset(n_students=args.students, seed=args.seed)
    write_dataset(ds, out)
    print(f"Wrote sample dataset to {out}")
    print(f"  courses:  {len(ds.courses)}")
    print(f"  teachers: {len(ds.teachers)}")
    print(f"  rooms:    {len(ds.rooms)}")
    print(f"  sections: {len(ds.sections)}")
    print(f"  students: {len(ds.students)}")
    return 0


def cmd_generate_sample_ms(args: argparse.Namespace) -> int:
    """Generate a synthetic full Middle School dataset (grades 6-8) per v2 §4.2.

    PoC-quality: per the skills-log lesson 2026-04-26, this generator is
    INFEASIBLE below ~200 students per grade because too few sections per
    cohort-required course let the master cluster two of them into the same
    scheme. The default n_per_grade=200 is the documented working floor.
    """
    out = Path(args.out)
    ds = make_full_ms_dataset(n_per_grade=args.per_grade, seed=args.seed)
    write_dataset(ds, out)
    print(f"Wrote synthetic MS sample dataset to {out}")
    print(f"  courses:  {len(ds.courses)}")
    print(f"  teachers: {len(ds.teachers)}")
    print(f"  rooms:    {len(ds.rooms)}")
    print(f"  sections: {len(ds.sections)}")
    print(f"  students: {len(ds.students)} ({args.per_grade} per grade × 3 grades)")
    if args.per_grade < 200:
        print(
            f"\nNOTE: per_grade={args.per_grade} is below the documented working floor (200). "
            "Solve may return INFEASIBLE because of cohort-feasibility constraints. "
            "Use --per-grade 200 or higher for a reliable solve.",
            file=sys.stderr,
        )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    ds = read_dataset(Path(args.in_dir))
    rep = validate_dataset(ds)
    print(rep.summary())
    return 0 if rep.is_ready else 2


def cmd_solve(args: argparse.Namespace) -> int:
    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    reports_dir = out_dir / "reports"
    exports_dir = out_dir / "powerschool"

    print(f"=== Stage 0: ingest + validate from {in_dir} ===")
    ds = read_dataset(in_dir)
    rep = validate_dataset(ds)
    print(rep.summary())
    if not rep.is_ready:
        print("\nABORTING: data has errors. Fix and re-run.", file=sys.stderr)
        return 2

    if args.coplanning:
        ds.config.hard.enforce_coplanning_groups = True
        print(f"Coplanning HARD enabled — {len(ds.coplanning_groups)} groups must share a free scheme")

    print(f"\n=== Stage 1: master schedule (sections={len(ds.sections)}) ===")
    master, _, m_status = solve_master(ds, time_limit_s=args.master_time, verbose=args.verbose)
    print(f"Status: {m_status}, assignments: {len(master)}")
    if not master:
        print("ABORTING: master schedule infeasible.", file=sys.stderr)
        return 3

    print(f"\n=== Stage 2: student assignment (mode={args.mode}, students={len(ds.students)}) ===")
    student_assigns, unmet, _, s_status = solve_students(ds, master, time_limit_s=args.student_time, mode=args.mode, verbose=args.verbose)
    print(f"Status: {s_status}, students placed: {len(student_assigns)}, unmet rank-1: {len(unmet)}")

    print("\n=== Stage 3: reports ===")
    md_path = write_reports(ds, master, student_assigns, unmet, reports_dir)
    kpi = compute_kpis(ds, master, student_assigns, unmet)
    print(kpi.summary())
    print(f"\nReports written to {reports_dir}")
    print(f"Markdown summary: {md_path}")

    print("\n=== Stage 4: PowerSchool export ===")
    export_powerschool(ds, master, student_assigns, exports_dir)
    print(f"PS-compatible CSVs written to {exports_dir}")

    if args.oneroster:
        oneroster_dir = out_dir / "oneroster"
        print("\n=== Stage 5: OneRoster export ===")
        write_oneroster(ds, master, student_assigns, oneroster_dir)
        print(f"OneRoster v1.1 CSVs written to {oneroster_dir}")

    return 0


def _parse_grade_arg(raw: str) -> int | list[int]:
    """Accept '12', '9,10,11,12', or 'all-hs' (shorthand for 9..12)."""
    s = raw.strip().lower()
    if s in ("all-hs", "hs", "all"):
        return [9, 10, 11, 12]
    if "," in s:
        return sorted({int(p.strip()) for p in s.split(",") if p.strip()})
    return int(s)


def cmd_import_ps(args: argparse.Namespace) -> int:
    """Read real Columbus xlsx files and write a canonical-CSV dataset."""
    demand = Path(args.demand)
    schedule = Path(args.schedule) if args.schedule else None
    out_dir = Path(args.out_dir)

    if not demand.exists():
        print(f"ERROR: demand file not found: {demand}", file=sys.stderr)
        return 2
    if schedule is not None and not schedule.exists():
        print(f"WARNING: schedule file not found, behavior matrix will be empty: {schedule}", file=sys.stderr)
        schedule = None

    grade_arg = _parse_grade_arg(args.grade) if isinstance(args.grade, str) else args.grade
    print(f"Reading Columbus xlsx files (grade={grade_arg})...")
    print(f"  demand:   {demand.name}")
    if schedule:
        print(f"  schedule: {schedule.name}")

    ds = build_dataset_from_columbus(demand, schedule, grade=grade_arg, year=args.year)
    print(f"\nIngested:")
    print(f"  courses:     {len(ds.courses)}")
    print(f"  teachers:    {len(ds.teachers)}")
    print(f"  rooms:       {len(ds.rooms)}")
    print(f"  sections:    {len(ds.sections)}")
    print(f"  students:    {len(ds.students)}")
    print(f"  separations: {len(ds.behavior.separations)}")
    print(f"  groupings:   {len(ds.behavior.groupings)}")

    rep = validate_dataset(ds)
    print()
    print(rep.summary())

    if not rep.is_ready:
        print("\nABORTING: data has errors. Fix and re-import.", file=sys.stderr)
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)
    write_dataset(ds, out_dir)
    print(f"\nCanonical CSVs written to {out_dir}")
    print(f"Next step: solve --in {out_dir} --out <out>")
    return 0


def cmd_scenarios(args: argparse.Namespace) -> int:
    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading dataset from {in_dir}...")
    ds = read_dataset(in_dir)
    rep = validate_dataset(ds)
    if not rep.is_ready:
        print("ABORTING: dataset has validation errors", file=sys.stderr)
        print(rep.summary(), file=sys.stderr)
        return 2

    preset = args.preset
    if preset not in PRESETS:
        print(f"Unknown preset '{preset}'. Available: {list(PRESETS.keys())}", file=sys.stderr)
        return 2

    specs = PRESETS[preset]
    print(f"Running {len(specs)} scenarios from preset '{preset}'...\n")
    results = run_scenarios(
        ds, specs,
        master_time=args.master_time,
        student_time=args.student_time,
        progress=True,
    )

    print("\n=== Comparison ===\n")
    md = format_comparison(results)
    print(md)

    out_path = out_dir / f"scenarios_{preset}.md"
    out_path.write_text(f"# Scenario comparison — preset `{preset}`\n\n{md}\n")
    print(f"\nWritten to {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="scheduler", description="Columbus scheduling engine — Grade 12 prototype")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate-sample", help="Generate Grade-12 sample CSVs")
    g.add_argument("--out", default="data/sample")
    g.add_argument("--students", type=int, default=130)
    g.add_argument("--seed", type=int, default=42)
    g.set_defaults(func=cmd_generate_sample)

    gms = sub.add_parser("generate-sample-ms",
                          help="Generate synthetic full MS sample CSVs (grades 6-8)")
    gms.add_argument("--out", default="data/sample_ms")
    gms.add_argument("--per-grade", type=int, default=200,
                     help="Students per grade (6/7/8). Default 200; ≥200 is the documented working floor.")
    gms.add_argument("--seed", type=int, default=42)
    gms.set_defaults(func=cmd_generate_sample_ms)

    v = sub.add_parser("validate", help="Validate a CSV dataset")
    v.add_argument("--in", dest="in_dir", default="data/sample")
    v.set_defaults(func=cmd_validate)

    s = sub.add_parser("solve", help="End-to-end ingest + solve + export")
    s.add_argument("--in", dest="in_dir", default="data/sample")
    s.add_argument("--out", dest="out_dir", default="data/exports")
    s.add_argument("--master-time", type=float, default=60.0)
    s.add_argument("--student-time", type=float, default=240.0)
    s.add_argument("--mode", choices=["single", "lexmin"], default="single",
                   help="single (default): weighted-sum with hard balance cap; lexmin: 2-phase (electives → groupings) with hard balance cap")
    s.add_argument("--oneroster", action="store_true",
                   help="Also write a OneRoster v1.1 CSV bundle to <out>/oneroster/")
    s.add_argument("--coplanning", action="store_true",
                   help="Enforce coplanning groups (HardConstraints.enforce_coplanning_groups). "
                        "Default OFF; turning ON costs ~50 unmet on real Columbus.")
    s.add_argument("--verbose", action="store_true")
    s.set_defaults(func=cmd_solve)

    sc = sub.add_parser("scenarios", help="Run a preset of scenarios and compare KPIs")
    sc.add_argument("--in", dest="in_dir", default="data/sample")
    sc.add_argument("--out", dest="out_dir", default="data/exports")
    sc.add_argument("--preset", default="default", help=f"One of: {list(PRESETS.keys())}")
    sc.add_argument("--master-time", type=float, default=20.0)
    sc.add_argument("--student-time", type=float, default=120.0)
    sc.set_defaults(func=cmd_scenarios)

    ip = sub.add_parser("import-ps", help="Import real Columbus xlsx files → canonical CSVs")
    ip.add_argument("--demand", required=True, help="Path to '1._STUDENTS_PER_COURSE_*.xlsx'")
    ip.add_argument("--schedule", default=None, help="Path to 'HS_Schedule_*.xlsx' (for groupings)")
    ip.add_argument("--out", dest="out_dir", default="data/columbus", help="Output dir for canonical CSVs")
    ip.add_argument("--grade", default="12",
                   help="Grade to ingest. One of: '12' (single), '9,10,11,12' (comma-separated), 'all-hs' (shorthand for 9..12)")
    ip.add_argument("--year", default="2026-2027")
    ip.set_defaults(func=cmd_import_ps)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
