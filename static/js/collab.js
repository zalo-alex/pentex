// Real-time collaborative presence + live value sync for the report editor.

import { zidIndexes } from './src/store.js'
import { renderPages } from './src/render.js'

const PAGE_NAMES = ['general', 'executive', 'traces', 'discovery', 'observations', 'findings', 'project']
const _TINYMCE_PREFIX = { description: 'desc', remediation: 'remed', poc: 'poc' }

let _socket = null
let _myUserId = null
let _reportId = null
let _suppressChange = false   // prevents echo when applying remote TinyMCE updates
let _renderTimeout = null

// ── Public API ───────────────────────────────────────────────────────────────

export function initCollab(reportId, userId) {
    _myUserId = userId
    _reportId = reportId

    _socket = io({ transports: ['websocket', 'polling'] })

    _socket.on('connect', () => {
        _socket.emit('join_report', { report_id: reportId })
    })

    _socket.on('users_updated', ({ users }) => {
        _updatePresenceBar(users)
        _updateNavDots(users)
        _updateFieldStates(users)
    })

    _socket.on('field_changed', ({ type, fieldId, value }) => {
        _suppressChange = true
        try {
            if (type === 'global')  _applyGlobalChange(fieldId, value)
            if (type === 'list')    _applyListChange(fieldId, value)
            if (type === 'finding') _applyFindingChange(fieldId, value)
            if (type === 'tinymce') _applyTinyMCEChange(fieldId, value)
            if (type === 'cvss')    _applyCvssChange(fieldId, value)
        } finally {
            _suppressChange = false
        }
        if (_renderTimeout) clearTimeout(_renderTimeout)
        _renderTimeout = setTimeout(() => { renderPages(); _renderTimeout = null }, 300)
    })

    // Listen for value changes dispatched by store.js initBind
    document.addEventListener('collab:field-change', ({ detail: { bindKey, value, parentBind, parentBindZid } }) => {
        if (_suppressChange || !_socket) return
        let type, fieldId
        if (parentBind && parentBindZid) {
            const idx = zidIndexes[parentBind]?.indexOf(parentBindZid) ?? -1
            if (idx < 0) return
            if (parentBind === 'pages.findings') {
                type = 'finding'
                fieldId = `finding.${idx}.${bindKey}`
            } else {
                // auditors, scopes, testAccess, diffusionTable, versionHistory, abbreviations…
                type = 'list'
                fieldId = `${parentBind}.${idx}.${bindKey}`
            }
        } else {
            type = 'global'
            fieldId = bindKey
        }
        _socket.emit('field_change', { report_id: _reportId, type, fieldId, value })
    })

    _observeAllListItems()
}

export function emitPageChange(page) {
    if (_socket) _socket.emit('page_change', { report_id: _reportId, page })
}

export function emitFieldFocus(fieldId) {
    if (_socket) _socket.emit('field_focus', { report_id: _reportId, field_id: fieldId })
}

export function emitFieldBlur(fieldId) {
    if (_socket) _socket.emit('field_blur', { report_id: _reportId, field_id: fieldId })
}

export function emitFieldChange(type, fieldId, value) {
    if (_suppressChange || !_socket) return
    _socket.emit('field_change', { report_id: _reportId, type, fieldId, value })
}

// ── Presence UI ──────────────────────────────────────────────────────────────

function _updatePresenceBar(users) {
    const bar = document.getElementById('collabPresence')
    if (!bar) return
    bar.innerHTML = ''
    users.forEach(user => {
        const el = document.createElement('div')
        el.className = 'collab-avatar' + (user.id === _myUserId ? ' collab-avatar-me' : '')
        el.style.background = user.color
        el.title = user.username + (user.page ? ` — ${user.page}` : '')
        el.textContent = user.username[0].toUpperCase()
        bar.appendChild(el)
    })
}

function _updateNavDots(users) {
    document.querySelectorAll('.collab-nav-dot').forEach(d => d.remove())
    const buttons = document.querySelectorAll('.nav .button')
    PAGE_NAMES.forEach((page, i) => {
        const btn = buttons[i]
        if (!btn) return
        users
            .filter(u => u.page === page && u.id !== _myUserId)
            .forEach(user => {
                const dot = document.createElement('span')
                dot.className = 'collab-nav-dot'
                dot.style.background = user.color
                dot.title = user.username
                btn.appendChild(dot)
            })
    })
}

function _updateFieldStates(users) {
    document.querySelectorAll('.collab-field-indicator').forEach(el => el.remove())
    document.querySelectorAll('[data-collab-locked]').forEach(el => {
        el.removeAttribute('disabled')
        el.removeAttribute('data-collab-locked')
        el.style.removeProperty('outline')
        el.style.removeProperty('cursor')
    })

    users.filter(u => u.id !== _myUserId && u.focused_field).forEach(user => {
        const el = _resolveFieldEl(user.focused_field)
        if (!el) return

        el.setAttribute('disabled', '')
        el.setAttribute('data-collab-locked', user.id)
        el.style.outline = `2px solid ${user.color}`
        el.style.cursor = 'not-allowed'

        const dot = document.createElement('span')
        dot.className = 'collab-field-indicator'
        dot.style.setProperty('--collab-color', user.color)
        dot.title = `${user.username} is editing this field`
        el.after(dot)
    })
}

/**
 * Resolve a fieldId to its DOM input element.
 *
 * Formats:
 *  - "global.clientName"              → top-level input
 *  - "finding.0.name"                 → input inside a finding [zid] element
 *  - "global.auditors.0.fullName"     → input inside a list-item [zid] element
 */
function _resolveFieldEl(fieldId) {
    // Finding input: "finding.{idx}.{subkey}"
    if (fieldId.startsWith('finding.')) {
        const parts = fieldId.split('.')
        const idx = parseInt(parts[1])
        const subkey = parts.slice(2).join('.')
        const zids = zidIndexes['pages.findings']
        if (!zids || idx >= zids.length) return null
        const findingEl = document.querySelector(`[zid="${zids[idx]}"]`)
        const el = findingEl?.querySelector(`[data-bind="${CSS.escape(subkey)}"]`)
        return (el && el.tagName !== 'DIV') ? el : null
    }

    // Generic list item: "{parentBind}.{idx}.{subkey}" where idx is numeric
    const parts = fieldId.split('.')
    if (parts.length >= 3) {
        const idx = parseInt(parts[parts.length - 2])
        if (!isNaN(idx)) {
            const subkey = parts[parts.length - 1]
            const parentBind = parts.slice(0, -2).join('.')
            const zids = zidIndexes[parentBind]
            if (zids && idx < zids.length) {
                const parentEl = document.querySelector(`[zid="${zids[idx]}"]`)
                const el = parentEl?.querySelector(`[data-bind="${CSS.escape(subkey)}"]`)
                return (el && el.tagName !== 'DIV') ? el : null
            }
        }
    }

    // Top-level global field: "global.clientName"
    const el = document.querySelector(`[data-bind="${CSS.escape(fieldId)}"]`)
    if (!el || el.dataset.listInput || el.closest('[zid]')) return null
    return (el.tagName !== 'DIV' && el.tagName !== 'SPAN') ? el : null
}

// ── Apply remote value changes ────────────────────────────────────────────────

function _applyGlobalChange(fieldId, value) {
    const el = document.querySelector(`[data-bind="${CSS.escape(fieldId)}"]`)
    if (!el) return
    if (el.type === 'checkbox') el.checked = value
    else el.value = value
    _setPath(window.dataStore, fieldId, value)
}

function _applyListChange(fieldId, value) {
    // fieldId: "{parentBind}.{idx}.{subkey}"  e.g. "global.auditors.0.fullName"
    const parts = fieldId.split('.')
    const idx = parseInt(parts[parts.length - 2])
    const subkey = parts[parts.length - 1]
    const parentBind = parts.slice(0, -2).join('.')

    const zids = zidIndexes[parentBind]
    if (!zids || isNaN(idx) || idx >= zids.length) return

    const parentEl = document.querySelector(`[zid="${zids[idx]}"]`)
    if (parentEl) {
        const input = parentEl.querySelector(`[data-bind="${CSS.escape(subkey)}"]`)
        if (input) {
            if (input.type === 'checkbox') input.checked = value
            else input.value = value
        }
    }

    const arr = _getPath(window.dataStore, parentBind)
    if (arr?.[idx] != null) arr[idx][subkey] = value
}

function _applyFindingChange(fieldId, value) {
    // fieldId: "finding.{idx}.{subkey}"
    const parts = fieldId.split('.')
    const idx = parseInt(parts[1])
    const subkey = parts.slice(2).join('.')
    const zids = zidIndexes['pages.findings']
    if (!zids || idx >= zids.length) return

    const findingEl = document.querySelector(`[zid="${zids[idx]}"]`)
    if (findingEl) {
        const input = findingEl.querySelector(`[data-bind="${CSS.escape(subkey)}"]`)
        if (input) input.value = value
    }
    if (window.dataStore.pages.findings[idx]) {
        window.dataStore.pages.findings[idx][subkey] = value
    }
}

function _applyCvssChange(fieldId, value) {
    // fieldId: "finding.{idx}.cvssObj", value: { AV, AC, PR, UI, S, C, I, A }
    const idx = parseInt(fieldId.split('.')[1])
    const zids = zidIndexes['pages.findings']
    if (!zids || idx >= zids.length) return
    const findingZid = zids[idx]

    const cvssSection = document.querySelector(`.cvss-section[data-finding="${findingZid}"]`)
    if (cvssSection && value) {
        Object.keys(value).forEach(metric => {
            const group = cvssSection.querySelector(`.metric-buttons[data-metric="${metric}"]`)
            if (!group) return
            group.querySelectorAll('button').forEach(b => b.classList.remove('active'))
            group.querySelector(`button[data-value="${value[metric]}"]`)?.classList.add('active')
        })
        if (typeof window.updateCvssDisplay === 'function') window.updateCvssDisplay(cvssSection)
    }
    if (window.dataStore.pages.findings[idx]) {
        window.dataStore.pages.findings[idx].cvssObj = value
    }
}

function _applyTinyMCEChange(fieldId, value) {
    // fieldId: "finding.{idx}.{field}"
    const parts = fieldId.split('.')
    const idx = parseInt(parts[1])
    const field = parts.slice(2).join('.')
    const zids = zidIndexes['pages.findings']
    if (!zids || idx >= zids.length) return
    const prefix = _TINYMCE_PREFIX[field]
    if (!prefix) return
    const ed = typeof tinymce !== 'undefined' && tinymce.get(`${prefix}-${zids[idx]}`)
    if (ed) ed.setContent(value)
    if (window.dataStore.pages.findings[idx]) {
        window.dataStore.pages.findings[idx][field] = value
    }
}

// ── List item focus/blur observation ─────────────────────────────────────────

/**
 * Attaches focus/blur listeners to all [zid][data-bind] list items in the
 * sidebar (auditors, scopes, findings inputs, etc.) — both existing ones and
 * any added later via MutationObserver.
 */
function _observeAllListItems() {
    const sidebar = document.querySelector('.sidebar')
    if (!sidebar) return

    // Existing items already in the DOM
    sidebar.querySelectorAll('[zid][data-bind]').forEach(el => _attachListeners(el))

    // Items added dynamically (new finding, new auditor row, etc.)
    new MutationObserver(mutations => {
        mutations.forEach(m => m.addedNodes.forEach(node => {
            if (node.nodeType !== 1) return
            if (node.getAttribute?.('zid') && node.dataset.bind) _attachListeners(node)
            node.querySelectorAll?.('[zid][data-bind]').forEach(el => _attachListeners(el))
        }))
    }).observe(sidebar, { childList: true, subtree: true })
}

function _attachListeners(el) {
    const parentBind = el.dataset.bind   // e.g. "global.auditors", "pages.findings"
    const isFindings = parentBind === 'pages.findings'

    el.querySelectorAll('[data-bind]').forEach(input => {
        const subkey = input.dataset.bind
        const buildFieldId = () => {
            const zid = el.getAttribute('zid')
            const idx = zidIndexes[parentBind]?.indexOf(zid) ?? -1
            if (idx < 0) return null
            return isFindings ? `finding.${idx}.${subkey}` : `${parentBind}.${idx}.${subkey}`
        }
        input.addEventListener('focus', () => { const fid = buildFieldId(); if (fid) emitFieldFocus(fid) })
        input.addEventListener('blur',  () => { const fid = buildFieldId(); if (fid) emitFieldBlur(fid) })
    })
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function _setPath(obj, path, value) {
    const keys = path.split('.')
    let cur = obj
    for (let i = 0; i < keys.length - 1; i++) {
        if (cur[keys[i]] == null) cur[keys[i]] = {}
        cur = cur[keys[i]]
    }
    cur[keys[keys.length - 1]] = value
}

function _getPath(obj, path) {
    return path.split('.').reduce((cur, key) => cur?.[key], obj)
}
