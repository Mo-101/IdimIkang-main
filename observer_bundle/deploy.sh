#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/idona/MoStar/idim-ikang-observer"
VENV_DIR="$APP_DIR/.venv"
DB_NAME="idim_ikang"

mkdir -p "$APP_DIR"

echo "[1/7] Copy bundle files into $APP_DIR"
cp scanner.py api.py outcome_tracker.py ecosystem.idim.config.js requirements.txt .env.example setup_db.sql "$APP_DIR"/

cd "$APP_DIR"

if [[ ! -f ".env" ]]; then
  cp .env.example .env
  echo "Created .env from .env.example — fill in DATABASE_URL / Telegram vars before first live run if needed."
fi

echo "[2/7] Creating Python virtual environment"
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo "[3/7] Installing Python dependencies"
pip install --upgrade pip
pip install -r requirements.txt

echo "[4/7] Creating PostgreSQL database and tables"
if psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
  echo "Database $DB_NAME already exists, skipping CREATE DATABASE"
  psql -d "$DB_NAME" -f setup_db.sql || true
else
  psql -f setup_db.sql
fi

echo "[5/7] Registering PM2 services"
pm2 start ecosystem.idim.config.js
pm2 save

echo "[6/7] Verifying PM2 status"
pm2 status

echo "[7/7] Deployment complete"
echo "API status:  http://localhost:8787/status"
echo "API signals: http://localhost:8787/signals"
echo "Kill switch: POST http://localhost:8787/kill"
