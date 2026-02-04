# AGENTS.md — quintus

## 1. Project Context
- **Name:** quintus
- **Purpose:** Single-User Hausverwaltung (Property Management)
- **Environment:** Debian 13 VM on Proxmox
- **User:** `quintus` (Home: `/home/quintus`)
- **Editor Preference:** **vi** (Strictly no nano)
- **Timezone:** Europe/Vienna

## 2. Tech Stack & Architecture
- **Language:** Python 3 (Virtualenv)
- **Framework:** Django (use the version pinned in `requirements.txt`)
- **Database:** SQLite (`db.sqlite3` in project root)
  - *Note:* System is single-user, but Cron jobs exist. Keep DB write transactions short to avoid locking.
  - *Cron rule:* Scheduled/import tasks must be **idempotent** (re-running must not create duplicates).
- **Frontend:** Django Templates (Tailwind optional later)
- **Server (later):** Gunicorn + systemd (reverse proxy handled externally if needed)

## 3. Directory Structure (Do not restructure without request)
- **Project Root (Git root):** `~/apps/quintus/`
- **manage.py:** located in project root
- **Django project package:** `core/` (settings.py, urls.py, asgi.py, wsgi.py)
- **Main Django app:** `webapp/` (models, views, templates, admin, management commands)
- **Virtualenv:** `.venv/` (Not committed)
- **Logs/Data:** `logs/` and any runtime data directories (Not committed)

## 4. Non-negotiables (Strict Rules)
- **Security:** NEVER commit secrets (passwords, keys). Use `.env` (ignored by git).
- **Simplicity:** Keep changes minimal. Prefer Django built-ins over complex third-party packages.
- **Workflow:** Codex pushes to GitHub `main`; server deploys via `git pull`.
  - Keep commits small and safe (main is deployed).
  - Do not change user-facing terminology unless requested.
- **Coding Style:**
  - Prefer Class-Based Views (CBVs) for standard CRUD.
  - Type hints are encouraged.

## 5. Quality Gates (Must Pass)
Before committing, ensure these run without error:
1. `python -m compileall .`
2. `python manage.py check`
3. `python manage.py test`
4. If models changed: ensure migrations are created and committed (`python manage.py makemigrations` and `python manage.py migrate`).
