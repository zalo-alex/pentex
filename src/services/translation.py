import difflib
import json
import os
import re

import requests

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'llm-config.json')

_LANG_NAMES = {'EN': 'English', 'FR': 'French'}

_TRANSLATED_FIELDS = ('title', 'vulnType', 'description', 'observation', 'remediation')


class TranslationError(Exception):
    pass


def _load_llm_config():
    if not os.path.isfile(_CONFIG_PATH):
        raise TranslationError(f'LLM config not found at {_CONFIG_PATH}')
    with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)
    try:
        provider = next(iter(config['provider'].values()))
        base_url = provider['options']['baseURL'].rstrip('/')
        api_key = provider['options']['apiKey']
        model = config['model'].split('/', 1)[1] if '/' in config['model'] else config['model']
    except (KeyError, StopIteration, IndexError) as e:
        raise TranslationError(f'Malformed llm-config.json: {e}')
    return base_url, api_key, model


def _chat_completion(system_prompt, user_content, timeout=180):
    base_url, api_key, model = _load_llm_config()
    try:
        resp = requests.post(
            f'{base_url}/chat/completions',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={
                'model': model,
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_content},
                ],
                'temperature': 0.2,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise TranslationError(f'LLM request failed: {e}')

    try:
        body = json.loads(resp.content.decode('utf-8'))
        return body['choices'][0]['message']['content'].strip()
    except (KeyError, IndexError, ValueError, UnicodeDecodeError) as e:
        raise TranslationError(f'Unexpected LLM response shape: {e}')


def _strip_code_fence(content):
    if not content.startswith('```'):
        return content
    content = content.strip('`')
    if content.startswith('json') or content.startswith('html'):
        content = content.split('\n', 1)[1] if '\n' in content else content[4:]
    return content.strip()


def translate_vulnerability_fields(fields, source_lang, target_lang):
    """Translate a dict of vulnerability text fields from source_lang to target_lang using the
    OpenAI-compatible chat completions endpoint configured in llm-config.json."""
    payload_in = {k: fields.get(k) or '' for k in _TRANSLATED_FIELDS}
    system_prompt = (
        f'You are a professional penetration testing report translator. Translate the JSON object fields '
        f'from {_LANG_NAMES.get(source_lang, source_lang)} to {_LANG_NAMES.get(target_lang, target_lang)}. '
        'Preserve any HTML tags exactly (translate only the text content between tags). '
        'Keep technical terms (CWE/CAPEC/OWASP identifiers, product/protocol names) unchanged. '
        'Respond with ONLY a JSON object using the exact same keys as the input, no other text.'
    )

    content = _strip_code_fence(_chat_completion(system_prompt, json.dumps(payload_in, ensure_ascii=False)))

    try:
        translated = json.loads(content)
    except json.JSONDecodeError as e:
        raise TranslationError(f'LLM did not return valid JSON: {e}')

    if not isinstance(translated, dict) or not all(k in translated for k in _TRANSLATED_FIELDS):
        raise TranslationError('LLM response is missing expected fields')

    return {k: translated.get(k) or '' for k in _TRANSLATED_FIELDS}


_TOKEN_RE = re.compile(r'\{\{\{?#?/?[^{}]*\}\}\}?|\$\([^)]*\)')


def _extract_tokens(content):
    return _TOKEN_RE.findall(content)


def translate_template_page(content, source_lang, target_lang, rules=None):
    """Translate the human-readable text of a Handlebars report-template page (.hbs) from
    source_lang to target_lang, leaving all Handlebars bindings/blocks, `$(...)` print tokens,
    HTML tags/attributes/classes and hrefs untouched. Raises TranslationError if the LLM's
    output doesn't preserve the exact same set of bindings as the source (safer than silently
    writing a template that would fail to render or drop a field).

    `rules` is an optional list of free-text terminology/wording instructions (see
    src/models.py's TranslationRule) that take priority over the LLM's default word choices —
    e.g. "Use \"malicious actor\" instead of \"attacker\"\"."""
    if not (content or '').strip():
        return content or ''

    system_prompt = (
        f'You are a professional translator localizing a penetration-testing report template from '
        f'{_LANG_NAMES.get(source_lang, source_lang)} to {_LANG_NAMES.get(target_lang, target_lang)}. '
        'The input is an HTML fragment mixed with Handlebars template syntax. '
        'Translate ONLY the human-readable prose and labels. '
        'Do NOT translate, modify, remove, reorder, or rename anything inside `{{...}}`, `{{{...}}}`, '
        '`{{#...}}`/`{{/...}}` blocks, or `$(...)` tokens — copy them through byte-for-byte. '
        'Do NOT change any HTML tags, attributes, class names, ids, inline styles, or href/src URLs. '
        'Preserve the exact structure, line breaks, and indentation of the input. '
        'Respond with ONLY the translated file content, no explanation, no markdown code fences.'
    )
    if rules:
        rules_block = '\n'.join(f'- {r}' for r in rules)
        system_prompt += (
            '\n\nAdditionally, apply these mandatory terminology/wording rules — they take '
            f'priority over your default word choices when they conflict:\n{rules_block}'
        )

    # Template pages (especially methodology.hbs-sized ones) can be much larger than a
    # vulnerability's individual fields and take longer for the LLM to translate; this runs
    # in a background job (see templates.py's translate job), not inline in a request, so a
    # generous timeout scaled to content size is safe.
    timeout = max(180, min(600, len(content) // 20))
    translated = _strip_code_fence(_chat_completion(system_prompt, content, timeout=timeout))

    if not translated.strip():
        raise TranslationError('LLM returned empty content')

    if _extract_tokens(translated) != _extract_tokens(content):
        raise TranslationError('Translated page does not preserve the original template bindings')

    return translated


_GUARD_CHARS = re.compile(r'[{<]')
_MIN_DIFF_RATIO = 0.5  # below this, treat as a wholesale rewrite rather than a wording tweak

# Tokenize Handlebars bindings and HTML tags as their own tokens (not merged with adjacent
# words like whitespace-splitting would do, e.g. "<h3>Vulnerability" staying one token) so a
# word change immediately next to an unchanged tag — extremely common in these .hbs files,
# e.g. "<h3>Description</h3>" — doesn't get swept into the same diff opcode as the tag.
_TOKENIZE_RE = re.compile(_TOKEN_RE.pattern + r'|<[^>]*>|\S+')


def detect_wording_changes(baseline_content, current_content):
    """Word-level diff between a page's last-LLM-output baseline and its current (possibly
    hand-edited) content. Returns a list of {'old': str, 'new': str} candidate wording changes.
    Anything touching a Handlebars binding (`{{`/`{{{`/`{{#...}}`) or an HTML tag (`<...>`) is
    guarded out, so only prose wording swaps are ever surfaced — not template-syntax or markup
    changes (which shouldn't occur given translate_template_page's own token-preservation check,
    but are excluded defensively regardless)."""
    baseline_words = _TOKENIZE_RE.findall(baseline_content or '')
    current_words = _TOKENIZE_RE.findall(current_content or '')
    if not baseline_words and not current_words:
        return []

    sm = difflib.SequenceMatcher(a=baseline_words, b=current_words, autojunk=False)
    if sm.ratio() < _MIN_DIFF_RATIO:
        # Wholesale rewrite (or the two aren't meaningfully related) — flattening every opcode
        # into a word-diff list would just be noise, not a useful review checklist.
        return []

    changes = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        old_text = ' '.join(baseline_words[i1:i2])
        new_text = ' '.join(current_words[j1:j2])
        if _GUARD_CHARS.search(old_text) or _GUARD_CHARS.search(new_text):
            continue
        if not old_text and not new_text:
            continue
        changes.append({'old': old_text, 'new': new_text})
    return changes
