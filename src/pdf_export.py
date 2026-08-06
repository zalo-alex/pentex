import os
import subprocess
import sys

# A4 at 96 CSS px/inch (210mm x 297mm). The template's print rules size each
# <page> as width: 100%; height: 100vh, so the viewport must already match
# A4's proportions before rendering - otherwise 100vh resolves against
# Chromium's default viewport (1280x720) instead of the physical page, and
# printToPDF pads/letterboxes the mismatched content to fit the A4 paper.
_A4_VIEWPORT = {'width': 794, 'height': 1123}

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def render_html_to_pdf(html: str) -> bytes:
    """Render a self-contained HTML document (as produced by compileHtml() in
    static/js/src/export.js) to PDF bytes using headless Chromium.

    This spawns a dedicated child process (`python -m src.pdf_export`) rather
    than calling playwright.sync_api inline, because this app's Flask-SocketIO
    now auto-selects async_mode='gevent' (gevent is in requirements.txt).
    Playwright's sync driver relies on real OS threads/pipes and is not
    greenlet-safe - running it inside a gevent-served request handler risks
    hangs or corruption if gevent's cooperative scheduler is monkey-patching
    threading/socket/subprocess. A separate OS process is never monkey-patched
    by the parent's gevent state, so this is safe regardless of which
    Flask-SocketIO async_mode ends up active.
    """
    result = subprocess.run(
        [sys.executable, '-m', 'src.pdf_export'],
        input=html.encode('utf-8'),
        capture_output=True,
        cwd=_PROJECT_ROOT,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f'PDF render subprocess failed: {result.stderr.decode(errors="replace")}')
    return result.stdout


def _render_sync(html: str) -> bytes:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport=_A4_VIEWPORT)
            page.set_content(html, wait_until='load')
            page.wait_for_timeout(1000)
            # Report templates can ship their own @page rule (e.g. margin:
            # var(--z-68px) var(--z-57px)) - Chromium's printToPDF honors a
            # CSS @page margin over the pdf()-call margin parameter
            # regardless of prefer_css_page_size (confirmed empirically: the
            # explicit margin=0 below was silently ignored while any @page
            # margin rule was present). The only reliable way to force a
            # true zero physical margin is to neutralize the CSS rule itself,
            # appended last so it wins the cascade.
            page.add_style_tag(content='@page { margin: 0 !important; size: A4 !important; }')
            return page.pdf(
                print_background=True,
                format='A4',
                margin={'top': '0', 'bottom': '0', 'left': '0', 'right': '0'},
            )
        finally:
            browser.close()


if __name__ == '__main__':
    _html = sys.stdin.buffer.read().decode('utf-8')
    sys.stdout.buffer.write(_render_sync(_html))
