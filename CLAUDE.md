# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PENTEX is a Flask-based web application for managing penetration testing reports. Security auditors can create and manage reports with an integrated vulnerability database, CVSS scoring, and Handlebars-based report section templates.

## Running the Application

```bash
source ./venv/bin/activate
python app.py
```

Runs on `http://0.0.0.0:5000`. Default admin credentials: `admin` / `admin` (auto-created on first startup).

## Database Management

```bash
flask db migrate -m "Description"
flask db upgrade
```

SQLite database at `instance/pentex.db`. Uses batch operations in migrations for SQLite compatibility.

## Architecture

### Backend (`app.py` + `src/`)

`app.py` (67 lines) registers five blueprints and auto-creates the admin user on startup:

| Blueprint | File | Responsibilities |
|-----------|------|-----------------|
| auth | `src/routes/auth.py` | Login, logout, profile/password change |
| reports | `src/routes/reports.py` | Report CRUD + JSON API (`/api/reports`) |
| vulnerabilities | `src/routes/vulnerabilities.py` | Vuln CRUD, CVSS parsing, `/api/vulnerabilities` |
| templates | `src/routes/templates.py` | List/validate `.hbs` template files |
| admin | `src/routes/admin.py` | User management, invite token flow |

**Models** (`src/models.py`): `User` (with `is_admin`), `InviteToken`, `Report` (user-scoped, stores rich HTML content), `Vulnerability` (global catalog with CVSS fields).

**Authorization**: `@login_required` for user routes, `@admin_required` (custom decorator in `admin.py`) for admin routes. Reports are ownership-checked per request.

### Frontend

**No build process** — vanilla JS, HTML5, CSS3.

**Report editor** (`templates/editor.html`): Sidebar with `data-bind` form fields tied to `window.dataStore` (see `static/js/src/store.js`) + TinyMCE rich text area. Auto-saves via `PUT /api/reports/<id>`.

**Key JS modules** (`static/js/src/`):
- `store.js` — reactive store with localStorage persistence; `data-bind` attributes on inputs auto-sync to nested store paths (e.g. `data-bind="global.clientName"`)
- `editor.js` — dynamic list items (auditors, scopes, etc.) using `addListItem()` / `removeListItem()`
- `templates.js` + `render.js` — Handlebars rendering pipeline that inserts template sections into TinyMCE
- `export.js` — PDF/print export
- `api.js` — fetch wrappers for all `/api/` endpoints

**`static/js/cvss.js`**: CVSS v3.1 calculator used in the vulnerability form.

**Handlebars templates** live in `static/pages/*.hbs`. The `/api/templates` endpoint lists them; the template manager page (`/templates`) also validates them (checks for `<page>` wrapper, lints CSS for hardcoded values).

### User Onboarding Flow

Admin creates user via `/admin` → server generates `InviteToken` → user visits `/invite/<token>` to set password → normal login.
