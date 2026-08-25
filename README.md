# Pentex

A Flask web application for managing penetration testing reports. Security auditors can collaboratively write reports with an integrated vulnerability database, CVSS v3.1 scoring, and a Handlebars-based template system for generating structured report sections.

## Features

- **Report editor** — TinyMCE rich text editor with auto-save, real-time multi-user presence (Socket.IO), and per-report access control
- **Vulnerability database** — global catalog with CVSS v3.1 scoring, severity classification, and insertion into reports
- **Template system** — Handlebars templates (`static/pages/*.hbs`) render structured sections (title page, findings, executive summary, etc.) directly into the editor
- **User management** — invite-only registration, admin panel, audit log
- **PDF export** — server-side rendering via headless Chromium (Playwright), matching report-specific styles
- **AI translation** *(optional)* — translate vulnerabilities and template pages via an OpenAI-compatible chat completions API, configured in `llm-config.json`

## Getting started

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

TinyMCE (self-hosted, GPL build) is gitignored and not committed to the repo — download it once and unpack it into `static/tinymce`:

```bash
curl -fsSL https://download.tiny.cloud/tinymce/community/tinymce_8.8.2.zip -o /tmp/tinymce.zip
unzip -q /tmp/tinymce.zip -d /tmp/tinymce_extract
mv /tmp/tinymce_extract/tinymce/js/tinymce static/tinymce
rm -rf /tmp/tinymce.zip /tmp/tinymce_extract
```

```bash
flask db upgrade
python app.py
```

The app runs on `http://localhost:5000`. On first startup a temporary admin password is printed to the console.

Building the Docker image instead? It fetches TinyMCE itself (pinned via `TINYMCE_VERSION` in the Dockerfile) — no manual step needed, see below.

## Environment variables

Create a `.env` file at the project root:

```env
SECRET_KEY=<random-secret>
FLASK_DEBUG=false
ALLOWED_ORIGIN=http://localhost:5000
LOG_LEVEL=INFO
```

## AI translation settings (optional)

Vulnerability and template-page translation call out to an OpenAI-compatible chat completions endpoint. Without this file the rest of the app works normally; only the translate actions fail. Create `llm-config.json` at the project root:

```json
{
  "provider": {
    "my-provider": {
      "options": {
        "baseURL": "https://api.example.com/v1",
        "apiKey": "<api-key>"
      }
    }
  },
  "model": "my-provider/<model-name>"
}
```

`baseURL` is queried at `<baseURL>/chat/completions`; `model` is sent as `<model-name>` (everything after the first `/`).

## Docker

```bash
docker compose up -d --build
```

Builds the image (fetching TinyMCE and Playwright's Chromium itself) and starts the app on `http://localhost:5000`, persisting `instance/` and `logs/` to the host via bind mounts. Override `SECRET_KEY`, `FLASK_DEBUG`, `ALLOWED_ORIGIN`, `LOG_LEVEL` with a `.env` file (same variables as above). To enable AI translation, uncomment the `llm-config.json` mount in `docker-compose.yml` once that file exists on the host.

Without compose: `docker build -t pentex . && docker run -p 5000:5000 -e SECRET_KEY=<random-secret> -v ./instance:/app/instance -v ./logs:/app/logs pentex`.

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

SQLite database is stored at `instance/pentex.db`