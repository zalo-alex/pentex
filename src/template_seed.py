import os
from flask import current_app
from src.models import db, Template
from src import template_storage

# Narrative report order (headers.hbs / styles.css are pinned, not part of this list).
_PAGE_ORDER = [
    'title-page.hbs',
    'contents-table.hbs',
    'version-history.hbs',
    'diffusion-table.hbs',
    'acronyms-table.hbs',
    'introduction.hbs',
    'test-overview.hbs',
    'scope-and-conditions.hbs',
    'methodology.hbs',
    'executive-summary.hbs',
    'findings.hbs',
    'figures.hbs',
    'reserves.hbs',
]


def seed_default_template():
    """Create the built-in default report template from static/pages/ on first run."""
    pages_dir = os.path.join(current_app.static_folder, 'pages')
    if not os.path.isdir(pages_dir):
        return

    tpl = Template(name='Default', is_default=True)
    db.session.add(tpl)
    db.session.flush()  # populate tpl.public_id before writing pages to disk

    for filename in sorted(os.listdir(pages_dir)):
        path = os.path.join(pages_dir, filename)
        if not os.path.isfile(path):
            continue
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        template_storage.write_page(tpl.public_id, filename, content)

    template_storage.write_page_order(tpl.public_id, _PAGE_ORDER)
    db.session.commit()
