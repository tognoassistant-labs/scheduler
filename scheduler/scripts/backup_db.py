"""Backup script para la SQLite del Colegio.

Ideal para correr en cron nocturno:
    0 2 * * * cd /opt/scheduler && .venv/bin/python scripts/backup_db.py

Hace una copia de la SQLite usando el VACUUM INTO de SQLite (consistent
backup mientras hay readers activos), comprime con gzip, y nombra el
archivo con timestamp.

Mantiene los últimos N backups (default 7), borra los más viejos.

Uso:
    .venv/bin/python scripts/backup_db.py \\
        --db data/columbus.sqlite \\
        --out data/backups/ \\
        --keep 7
"""
from __future__ import annotations

import argparse
import gzip
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def backup_db(db_path: Path, out_dir: Path, keep: int = 7) -> Path:
    if not db_path.exists():
        print(f"❌ DB no encontrada: {db_path}")
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    raw_backup = out_dir / f"columbus_backup_{ts}.sqlite"
    gz_backup = out_dir / f"columbus_backup_{ts}.sqlite.gz"

    # Use VACUUM INTO for consistent backup
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(f"VACUUM INTO '{raw_backup}'")
    finally:
        conn.close()

    # Compress with gzip
    with raw_backup.open("rb") as fin:
        with gzip.open(gz_backup, "wb", compresslevel=6) as fout:
            shutil.copyfileobj(fin, fout)
    raw_backup.unlink()

    size_mb = gz_backup.stat().st_size / 1024 / 1024
    print(f"✅ Backup → {gz_backup} ({size_mb:.2f} MB)")

    # Cleanup viejos
    backups = sorted(out_dir.glob("columbus_backup_*.sqlite.gz"))
    if len(backups) > keep:
        to_remove = backups[:-keep]
        for old in to_remove:
            old.unlink()
            print(f"  🗑 borrado backup viejo: {old.name}")

    print(f"  📦 backups conservados: {min(len(backups), keep)}/{keep}")
    return gz_backup


def restore_db(backup_path: Path, target: Path, force: bool = False) -> None:
    if not backup_path.exists():
        print(f"❌ Backup no encontrado: {backup_path}")
        sys.exit(1)
    if target.exists() and not force:
        print(f"❌ DB destino ya existe: {target}. Usa --force para sobrescribir.")
        sys.exit(1)

    # Decompress if .gz
    if backup_path.suffix == ".gz":
        with gzip.open(backup_path, "rb") as fin:
            with target.open("wb") as fout:
                shutil.copyfileobj(fin, fout)
    else:
        shutil.copy(backup_path, target)
    size_kb = target.stat().st_size / 1024
    print(f"✅ Restore → {target} ({size_kb:.1f} KB)")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=False)

    p.add_argument("--db", default="data/columbus.sqlite",
                   help="Ruta a la BD a respaldar")
    p.add_argument("--out", default="data/backups",
                   help="Directorio donde guardar backups")
    p.add_argument("--keep", type=int, default=7,
                   help="Cuántos backups conservar (default 7)")

    # restore subcommand
    sp = sub.add_parser("restore", help="Restaurar desde un backup")
    sp.add_argument("--from", dest="from_path", required=True,
                    help="Ruta al backup (.sqlite.gz o .sqlite)")
    sp.add_argument("--to", dest="to_path", default="data/columbus.sqlite",
                    help="Ruta destino")
    sp.add_argument("--force", action="store_true",
                    help="Sobrescribir si el destino existe")

    args = p.parse_args()

    if args.cmd == "restore":
        restore_db(Path(args.from_path), Path(args.to_path), force=args.force)
    else:
        backup_db(Path(args.db), Path(args.out), keep=args.keep)


if __name__ == "__main__":
    main()
