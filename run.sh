#!/usr/bin/env bash
# run.sh — Clipper v2 (FastAPI backend + Vite frontend)
# ./run.sh          → backend + frontend birlikte (dev)
# ./run.sh backend  → sadece FastAPI (port 8000)
# ./run.sh frontend → sadece Vite (port 5173)
# ./run.sh test     → backend ve frontend testlerini %95+ coverage ile çalıştırır
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"
MODE="${1:-dev}"

# ── NVM / Node ────────────────────────────────────────────────────
NODE_BIN="$HOME/.nvm/versions/node/v24.14.0/bin"
export PATH="$NODE_BIN:$PATH"
export NVM_DIR="$HOME/.nvm"
if [ -s "$NVM_DIR/nvm.sh" ]; then
    \. "$NVM_DIR/nvm.sh" --no-use 2>/dev/null || true
fi

# ── Test Modu ─────────────────────────────────────────────────────
if [ "$MODE" = "test" ]; then
    echo "=================================================="
    echo "🧪 BACKEND TESTLERİ KOŞULUYOR (Hedef: >= %95)"
    echo "=================================================="
    .venv/bin/pytest tests/test_backend_*.py tests/test_api*.py --cov=backend --cov-report=term-missing --cov-fail-under=95

    echo ""
    echo "=================================================="
    echo "🎨 FRONTEND TESTLERİ KOŞULUYOR (Hedef: >= %95)"
    echo "=================================================="
    cd "$DIR/frontend" && npm run test:coverage
    cd "$DIR"

    echo ""
    echo "🎉 TÜM TESTLER BAŞARIYLA GEÇTİ (Backend & Frontend >= %95 Kapsama!)"
    exit 0
fi

# ── Port Temizliği ────────────────────────────────────────────────
if [ "$MODE" = "dev" ] || [ "$MODE" = "backend" ]; then
    fuser -k 8000/tcp 2>/dev/null || true
fi
if [ "$MODE" = "dev" ] || [ "$MODE" = "frontend" ]; then
    fuser -k 5173/tcp 2>/dev/null || true
fi

# ── Python virtualenv ─────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "⚙️  Virtualenv oluşturuluyor..."
    python3 -m venv .venv
fi
echo "📦 Python bağımlılıkları kontrol ediliyor..."
.venv/bin/pip install -e ".[dev]" --quiet

cleanup() {
    echo ""
    echo "🛑 Clipper durduruluyor..."
    [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null || true
    fuser -k 8000/tcp 2>/dev/null || true
    fuser -k 5173/tcp 2>/dev/null || true
    exit 0
}
trap cleanup EXIT INT TERM

# ── Backend (FastAPI + uvicorn) ───────────────────────────────────
if [ "$MODE" = "backend" ] || [ "$MODE" = "dev" ]; then
    echo "🚀 FastAPI → http://localhost:8000  |  Docs → http://localhost:8000/docs"
    if [ "$MODE" = "dev" ]; then
        .venv/bin/uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 &
        BACKEND_PID=$!
        echo "   Backend PID: $BACKEND_PID"
    else
        exec .venv/bin/uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
    fi
fi

# ── Frontend (Vite dev server) ────────────────────────────────────
if [ "$MODE" = "frontend" ] || [ "$MODE" = "dev" ]; then
    FDIR="$DIR/frontend"
    if [ ! -d "$FDIR/node_modules" ]; then
        echo "📦 npm bağımlılıkları yükleniyor..."
        cd "$FDIR" && npm install && cd "$DIR"
    fi
    echo "🎨 Vite → http://localhost:5173"
    cd "$FDIR" && npm run dev
fi

[ -n "$BACKEND_PID" ] && wait $BACKEND_PID
