#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON=".venv/bin/python"

echo "Prüfe Django ..."
"$PYTHON" manage.py check
"$PYTHON" manage.py makemigrations --check --dry-run

echo "Wende Migrationen an ..."
"$PYTHON" manage.py migrate --noinput

echo "Aktualisiere statische Dateien ..."
"$PYTHON" manage.py collectstatic --noinput

echo "Starte Quintus neu ..."
sudo systemctl restart quintus

echo "Prüfe Dienst ..."
sudo systemctl is-active --quiet quintus

echo "Quintus wurde erfolgreich aktualisiert."
