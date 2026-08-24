import { tinymceConfig } from "./constants.js"
import { saveLocal } from "./store.js"
import { emitFieldChange, emitFieldFocus, emitFieldBlur } from "../collab.js"
import { WSTG_CATEGORIES } from "./wstg_catalog.js"

export { WSTG_CATEGORIES }

let _initialized = false
const _proofEditorsInit = new Set()

function _escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

// ── Rows / categories markup — reuses the app's existing collapsible
// editor-section (findings' Description/Observation/etc.) and list-input-item
// (auditors/scopes/etc.) components rather than introducing new ones. ────────

function _rowHtml(test) {
    return `<div class="list-input-item wstg-test-row" data-test-id="${test.id}">
        <div class="wstg-test-main-line">
            <span class="wstg-test-id">${test.id}</span>
            <span class="wstg-test-name">${test.name}</span>
            <button type="button" class="wstg-tested-btn" data-bind="global.wstgResults.${test.id}.tested">Tested</button>
            <div class="wstg-finding-picker">
                <button type="button" class="wstg-finding-toggle" title="Link a finding">+</button>
                <div class="wstg-finding-menu" hidden></div>
            </div>
        </div>
        <div class="wstg-finding-badges"></div>
    </div>`
}

function _categoryHtml(cat) {
    const rows = cat.tests.map(_rowHtml).join('')
    return `<div class="editor-section collapsed" data-cat-id="${cat.id}">
        <div class="editor-header" onclick="toggleEditor(this)">
            <span>4.${cat.num} &mdash; ${cat.name}</span>
            <span class="editor-toggle">▶</span>
        </div>
        <div class="editor-content" style="display:none">
            <div class="list-input-container wstg-test-list">${rows}</div>
            <label class="label-input">
                Proof of testing
                <textarea id="wstg-proof-${cat.id}" placeholder="Methodology, evidence and results for ${cat.name}"></textarea>
            </label>
        </div>
    </div>`
}

// ── Proof-of-testing rich text (lazy: only initialized the first time a category is expanded) ──

function _initProofEditor(cat) {
    const id = `wstg-proof-${cat.id}`
    const initialContent = (window.dataStore.global.wstgProof || {})[cat.id] || ''

    tinymce.init({
        ...tinymceConfig,
        selector: `#${id}`,
        // The shared config fixes every editor at 400px, sized for a finding's
        // full description. A category's proof-of-testing note is usually a lot
        // shorter, so grow-to-content instead of always reserving 400px of mostly
        // empty space.
        plugins: `${tinymceConfig.plugins} autoresize`,
        height: 160,
        min_height: 160,
        max_height: 500,
        autoresize_bottom_margin: 16,
        images_upload_handler: (blobInfo) => new Promise((resolve) => {
            const base64 = blobInfo.base64()
            resolve('data:' + blobInfo.blob().type + ';base64,' + base64)
        }),
        setup: (editor) => {
            editor.on('init', () => {
                if (initialContent) editor.setContent(initialContent)
            })
            editor.on('change keyup', () => {
                updateData(() => {
                    const content = DOMPurify.sanitize(editor.getContent())
                    if (!window.dataStore.global.wstgProof) window.dataStore.global.wstgProof = {}
                    window.dataStore.global.wstgProof[cat.id] = content
                    saveLocal()
                    emitFieldChange('tinymce', `wstgProof.${cat.id}`, content)
                })
            })
            editor.on('focus', () => emitFieldFocus(`wstgProof.${cat.id}`))
            editor.on('blur', () => emitFieldBlur(`wstgProof.${cat.id}`))
        },
        license_key: 'gpl'
    })
}

function _ensureProofEditor(catId) {
    if (_proofEditorsInit.has(catId)) return
    _proofEditorsInit.add(catId)
    const cat = WSTG_CATEGORIES.find(c => c.id === catId)
    if (cat) _initProofEditor(cat)
}

// ── Tested toggle ────────────────────────────────────────────────────────────

function _setTestedState(row) {
    const results = window.dataStore.global.wstgResults || {}
    const btn = row.querySelector('.wstg-tested-btn')
    btn.classList.toggle('active', !!(results[row.dataset.testId] || {}).tested)
}

function _toggleTested(row) {
    const testId = row.dataset.testId
    updateData(() => {
        if (!window.dataStore.global.wstgResults) window.dataStore.global.wstgResults = {}
        if (!window.dataStore.global.wstgResults[testId]) window.dataStore.global.wstgResults[testId] = {}
        const value = !window.dataStore.global.wstgResults[testId].tested
        window.dataStore.global.wstgResults[testId].tested = value
        saveLocal()
        emitFieldChange('global', `global.wstgResults.${testId}.tested`, value)
    })
    _setTestedState(row)
}

// ── Finding picker (badges + popover, using the app's tag-chip / pill-btn look) ──

function _findingName(idx) {
    const findings = (window.dataStore.pages && window.dataStore.pages.findings) || []
    const f = findings[idx]
    return (f && f.name) || `Finding ${idx + 1}`
}

function _selectedIndexes(testId) {
    const results = window.dataStore.global.wstgResults || {}
    return ((results[testId] || {}).findingIndexes) || []
}

function _badgesHtml(testId) {
    return _selectedIndexes(testId).map(idx =>
        `<span class="tag-chip wstg-finding-badge" title="${_escapeHtml(_findingName(idx))}">VULN-${idx + 1}<button type="button" class="tag-chip-remove" data-remove-idx="${idx}">×</button></span>`
    ).join('')
}

function _menuHtml(testId) {
    const findings = (window.dataStore.pages && window.dataStore.pages.findings) || []
    if (!findings.length) return `<div class="wstg-finding-empty">No findings yet</div>`

    const selected = new Set(_selectedIndexes(testId))
    return findings.map((f, idx) =>
        `<button type="button" class="pill-btn wstg-finding-option${selected.has(idx) ? ' active' : ''}" data-idx="${idx}">VULN-${idx + 1} &mdash; ${_escapeHtml(f.name || `Finding ${idx + 1}`)}</button>`
    ).join('')
}

function _renderPicker(row) {
    row.querySelector('.wstg-finding-badges').innerHTML = _badgesHtml(row.dataset.testId)
    row.querySelector('.wstg-finding-menu').innerHTML = _menuHtml(row.dataset.testId)
}

export function refreshWstgFindingOptions() {
    document.querySelectorAll('.wstg-test-row').forEach(_renderPicker)
}

function _closeAllMenus() {
    document.querySelectorAll('.wstg-finding-menu').forEach((menu) => { menu.hidden = true })
}

function _toggleFinding(row, idx) {
    const testId = row.dataset.testId
    updateData(() => {
        if (!window.dataStore.global.wstgResults) window.dataStore.global.wstgResults = {}
        if (!window.dataStore.global.wstgResults[testId]) window.dataStore.global.wstgResults[testId] = {}
        const current = window.dataStore.global.wstgResults[testId].findingIndexes || []
        const pos = current.indexOf(idx)
        window.dataStore.global.wstgResults[testId].findingIndexes = pos === -1
            ? [...current, idx]
            : current.filter(i => i !== idx)
        saveLocal()
    })
    _renderPicker(row)
}

// ── Public API ───────────────────────────────────────────────────────────────

export function initWstgUI() {
    if (_initialized) return
    _initialized = true

    const container = document.getElementById('wstgSidebarContainer')
    if (!container) return

    container.innerHTML = WSTG_CATEGORIES.map(_categoryHtml).join('')
    document.querySelectorAll('.wstg-test-row').forEach(_setTestedState)

    container.addEventListener('click', (e) => {
        const header = e.target.closest('.editor-header')
        if (header) {
            // toggleEditor(header) already ran via the inline onclick handler (it
            // fires before this delegated listener sees the bubbled event) — just
            // lazily spin up the rich text editor the first time it's revealed.
            const section = header.closest('.editor-section')
            if (!section.classList.contains('collapsed')) _ensureProofEditor(section.dataset.catId)
            return
        }

        const row = e.target.closest('.wstg-test-row')
        if (!row) return

        if (e.target.closest('.wstg-tested-btn')) {
            _toggleTested(row)
            return
        }

        const toggleBtn = e.target.closest('.wstg-finding-toggle')
        if (toggleBtn) {
            const menu = row.querySelector('.wstg-finding-menu')
            const wasHidden = menu.hidden
            _closeAllMenus()
            menu.hidden = !wasHidden
            return
        }

        const removeBtn = e.target.closest('.wstg-finding-badge .tag-chip-remove')
        if (removeBtn) {
            _toggleFinding(row, parseInt(removeBtn.dataset.removeIdx, 10))
            return
        }

        const option = e.target.closest('.wstg-finding-option')
        if (option) {
            _toggleFinding(row, parseInt(option.dataset.idx, 10))
        }
    })

    document.addEventListener('click', (e) => {
        if (!e.target.closest('.wstg-finding-picker')) _closeAllMenus()
    })

    refreshWstgFindingOptions()
}

export function refreshWstgUI() {
    document.querySelectorAll('.wstg-test-row').forEach(_setTestedState)
    refreshWstgFindingOptions()

    // Any category expanded before the report finished loading already lazily
    // initialized its editor with stale (empty) content — refresh it now.
    const proof = window.dataStore.global.wstgProof || {}
    _proofEditorsInit.forEach((catId) => {
        if (!proof[catId]) return
        const editor = typeof tinymce !== 'undefined' && tinymce.get(`wstg-proof-${catId}`)
        if (editor) editor.setContent(proof[catId])
    })
}
