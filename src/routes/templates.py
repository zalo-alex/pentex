import os
import re
from flask import Blueprint, render_template, jsonify, request, abort
from flask_login import login_required

templates_bp = Blueprint('templates_bp', __name__)

PAGES_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'static', 'pages')


def _list_templates():
    templates = []
    pages_dir = os.path.normpath(PAGES_DIR)
    if not os.path.isdir(pages_dir):
        return templates

    for filename in sorted(os.listdir(pages_dir)):
        if os.path.isdir(os.path.join(pages_dir, filename)):
            continue
        filepath = os.path.join(pages_dir, filename)
        with open(filepath, 'r') as f:
            content = f.read()
        templates.append({
            'filename': filename,
            'content': content,
        })
    return templates

def analyze_css(content):
    results = []
    static_value_regex = r"(?<![z\d-])(-?\d+(?:\.\d+)?(?:cm|mm|Q|in|pc|pt|px|em|ex|ch|rem|lh|vw|vh|vmin|vmax))"
    for i, line in enumerate(content.splitlines(), 1):
        matches = re.findall(static_value_regex, line)
        if not matches:
            continue

        result = {'line_index': i, 'matches': [], 'line': line, 'message': 'Use var(--z-10px) format instead'}
        for match in matches:
            if match not in result['matches']:
                result['matches'].append(match)

        results.append(result)
    return results

def analyze_hbs(filename, content):
    if filename == "headers.hbs":
        if '<header' not in content:
            return [{
                'line_index': 0,
                'matches': [],
                'line': 'Missing <header>',
                'message': ''
            }]
        elif '<footer' not in content:
            return [{
                'line_index': 0,
                'matches': [],
                'line': 'Missing <footer>',
                'message': ''
            }]
    else:
        if not content.startswith('<page'):
            return [{
                'line_index': 0,
                'matches': [],
                'line': 'Missing <page> at the beginning of the file',
                'message': ''
            }]
    return []

def analyze_template(filename, content):
    if filename.endswith('.css'):
        return analyze_css(content)
    elif filename.endswith('.hbs'):
        return analyze_hbs(filename, content)
    return []

def analyze_templates(templates):
    results = []
    for template in templates:
        result = analyze_template(template['filename'], template['content'])
        template["result"] = result
        results.append(template)
    return results

@templates_bp.route('/templates')
@login_required
def index():
    templates = _list_templates()
    return render_template('templates.html', templates=analyze_templates(templates))


@templates_bp.route('/api/templates')
@login_required
def api_list():
    templates = _list_templates()
    return jsonify(templates)