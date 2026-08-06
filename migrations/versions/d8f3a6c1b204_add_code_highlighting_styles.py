"""add code block syntax highlighting styles to existing template stylesheets

Revision ID: d8f3a6c1b204
Revises: c9d4e1f83a56
Create Date: 2026-07-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd8f3a6c1b204'
down_revision = 'c9d4e1f83a56'
branch_labels = None
depends_on = None

MARKER = '/* ─── CODE BLOCKS (TinyMCE codesample + Prism.js highlighting) ───────── */'

CODE_HIGHLIGHT_CSS = MARKER + """

:root {
    --code-bg:          #0c1b2e;
    --code-text:        #cdd9e5;
    --code-comment:     #7d93ad;
    --code-keyword:     #5aa6ff;
    --code-string:      #7ee2b8;
    --code-function:    #f2c572;
    --code-number:      #c9a8ff;
    --code-punctuation: #9fb2c7;
}

pre[class*="language-"] {
    background: var(--code-bg);
    color: var(--code-text);
    border-left: var(--z-4px) solid var(--accent);
    padding: var(--z-16px) var(--z-19px);
    font-family: "Consolas", "Courier New", monospace;
    font-size: var(--z-11px);
    white-space: pre-wrap;
    word-break: break-word;
    margin: var(--z-8px) 0 var(--z-13px) 0;
    line-height: 1.7;
}

code[class*="language-"] {
    background: none;
    color: inherit;
    font-family: inherit;
    font-size: var(--z-16px);
    white-space: inherit;
}

.token.comment,
.token.prolog,
.token.doctype,
.token.cdata {
    color: var(--code-comment);
    font-style: italic;
}

.token.keyword,
.token.selector,
.token.important,
.token.atrule {
    color: var(--code-keyword);
}

.token.string,
.token.attr-value,
.token.char,
.token.builtin {
    color: var(--code-string);
}

.token.function,
.token.tag,
.token.class-name {
    color: var(--code-function);
}

.token.number,
.token.boolean,
.token.constant,
.token.symbol {
    color: var(--code-number);
}

.token.punctuation,
.token.operator,
.token.entity,
.token.attr-name {
    color: var(--code-punctuation);
}
"""


def upgrade():
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, content FROM template_page WHERE filename = 'styles.css'"
    )).fetchall()
    for row in rows:
        content = row.content or ''
        if MARKER in content:
            continue
        conn.execute(
            sa.text("UPDATE template_page SET content = :content WHERE id = :id"),
            {'content': content + '\n' + CODE_HIGHLIGHT_CSS, 'id': row.id},
        )


def downgrade():
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, content FROM template_page WHERE filename = 'styles.css'"
    )).fetchall()
    for row in rows:
        content = row.content or ''
        idx = content.find(MARKER)
        if idx == -1:
            continue
        conn.execute(
            sa.text("UPDATE template_page SET content = :content WHERE id = :id"),
            {'content': content[:idx].rstrip() + '\n', 'id': row.id},
        )
