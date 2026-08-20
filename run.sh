#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

if [ ! -d ".venv" ]; then
    echo "Virtual environment bulunamadı, oluşturuluyor..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

echo "🚀 YouTube Most Replayed Clipper başlatılıyor..."
.venv/bin/streamlit run ui/app.py --server.port=8501 --server.headless=true
