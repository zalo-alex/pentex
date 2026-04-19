# Pentex

A Flask web application for managing penetration testing reports. Security auditors can collaboratively write reports with an integrated vulnerability database, CVSS v3.1 scoring, and a Handlebars-based template system for generating structured report sections.

## Features

- **Report editor** — TinyMCE rich text editor with auto-save, real-time multi-user presence (Socket.IO), and per-report access control
- **Vulnerability database** — global catalog with CVSS v3.1 scoring, severity classification, and insertion into reports
- **Template system** — Handlebars templates (`static/pages/*.hbs`) render structured sections (title page, findings, executive summary, etc.) directly into the editor
- **User management** — invite-only registration, admin panel, audit log
- **PDF export** — browser print pipeline with report-specific styles

## Getting started

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

flask db upgrade
python app.py
```

The app runs on `http://localhost:5000`. On first startup a temporary admin password is printed to the console.

## Environment variables

Create a `.env` file at the project root:

```env
SECRET_KEY=<random-secret>
FLASK_DEBUG=false
ALLOWED_ORIGIN=http://localhost:5000
```

## Project structure

```
app.py                  Flask app, Socket.IO handlers, blueprint registration
src/
  models.py             SQLAlchemy models (User, Report, Vulnerability, InviteToken, Log)
  log.py                Audit logging helper
  routes/
    auth.py             Login, logout, password change, invite flow
    reports.py          Report CRUD + /api/reports JSON API
    vulnerabilities.py  Vulnerability CRUD + /api/vulnerabilities
    templates.py        Template listing + validation
    admin.py            User management, categories, audit log viewer
static/
  js/src/
    store.js            Reactive data store with localStorage + data-bind wiring
    editor.js           Dynamic list items (auditors, scopes, findings)
    render.js           Handlebars rendering pipeline → TinyMCE
    templates.js        Template loader and section insertion
    api.js              Fetch wrappers for all API endpoints
    export.js           PDF/print export
  pages/*.hbs           Handlebars report section templates
  js/cvss.js            CVSS v3.1 interactive calculator
templates/              Jinja2 HTML templates
migrations/             Flask-Migrate / Alembic schema migrations
```

## User onboarding

Admin creates a user → invite token is generated → user visits `/invite/<token>` to set their password → normal login. Self-registration is disabled.

## Database management

```bash
flask db migrate -m "description"
flask db upgrade
```

SQLite database is stored at `instance/pentex.db` (not committed to git).
