#!/usr/bin/env bash
# Arranca la app en modo local. Uso: ./start_local.sh [--port 8501]
# Sin APP_PASSWORD = sin gate (modo desarrollo).
# Con APP_PASSWORD set en el shell = pide password.
set -euo pipefail

cd "$(dirname "$0")"

PORT="${PORT:-8501}"
if [[ "${1:-}" == "--port" && -n "${2:-}" ]]; then
    PORT="$2"
fi

# Primer arranque: crear venv si no existe
if [[ ! -d .venv ]]; then
    echo "→ Creando virtual environment (.venv) ..."
    python3.12 -m venv .venv 2>/dev/null || python3 -m venv .venv
    .venv/bin/pip install --quiet --upgrade pip
    echo "→ Instalando dependencias ..."
    .venv/bin/pip install --quiet -r requirements.txt
fi

# Default: SQLite local en data/columbus.sqlite
export COLUMBUS_DB="${COLUMBUS_DB:-$(pwd)/data/columbus.sqlite}"
mkdir -p "$(dirname "$COLUMBUS_DB")"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Columbus Scheduler — modo local"
echo "═══════════════════════════════════════════════════════"
echo "  URL:   http://localhost:$PORT"
echo "  DB:    $COLUMBUS_DB"
if [[ -n "${APP_PASSWORD:-}" ]]; then
    echo "  Auth:  ON (password gate activo)"
else
    echo "  Auth:  OFF (acceso libre — solo para revisión local)"
fi
echo "═══════════════════════════════════════════════════════"
echo ""
echo "Ctrl+C para detener."
echo ""

exec .venv/bin/streamlit run app.py \
    --server.port "$PORT" \
    --server.address 127.0.0.1 \
    --server.headless true \
    --browser.gatherUsageStats false
