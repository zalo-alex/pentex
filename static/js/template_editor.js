import Handlebars from "/static/js/src/handlebars.js"

Handlebars.registerHelper('or', (...args) => args.slice(0, -1).some(Boolean));

function _csrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.content ?? ''
}

// Sample data used to render the live preview — templates aren't tied to any
// real report here, so we feed a representative placeholder context covering
// the fields the built-in page templates commonly reference.
const SAMPLE_DATA = {
    clientName: "Example Corp",
    targetName: "example.com",
    testType: "Web",
    approaches: ["Black Box"],
    blackbox: true, graybox: false, whitebox: false,
    reference: "PT-2026-001",
    revision: "1.0",
    abbreviations: [{ abbreviation: "XSS", definition: "Cross-Site Scripting" }],
    auditors: [{ userId: 1, fullName: "Jane Auditor", email: "jane@example.com" }],
    scopes: [{ name: "example.com", description: "Main web application" }],
    testAccess: [{ type: "Credentials", detail: "user / user123" }],
    diffusionTable: [{ name: "John Client", role: "CISO", date: "2026-01-01" }],
    versionHistory: [{ version: "1.0", date: "2026-01-01", author: "Jane Auditor", changes: "Initial version", description: "" }],
    findings: [{ name: "Sample Finding", description: "Sample description.", remediation: "Sample remediation.", severity: "High", index: 1 }],
    figures: [],
    index: 1,
    lastVersion: () => "1.0"
}

const pages = {}
for (const page of _initialPages) {
    pages[page.filename] = { content: page.content, result: page.result, savedContent: page.content }
}

function isPageDirty(filename) {
    return pages[filename].content !== pages[filename].savedContent
}

function hasUnsavedChanges() {
    return Object.keys(pages).some(isPageDirty)
}

let currentFilename = null
let monacoEditor = null
let previewTimer = null
let cssContent = ''

function analyzeCss(content) {
    const results = []
    const re = /(?<![z\d-])(-?\d+(?:\.\d+)?(?:cm|mm|Q|in|pc|pt|px|em|ex|ch|rem|lh|vw|vh|vmin|vmax))/g
    content.split('\n').forEach((line, idx) => {
        const matches = [...new Set([...line.matchAll(re)].map(m => m[0]))]
        if (matches.length === 0) return
        results.push({ line_index: idx + 1, matches, line, message: 'Use var(--z-10px) format instead' })
    })
    return results
}

function analyzeHbs(filename, content) {
    if (filename === 'headers.hbs') {
        if (!content.includes('<header')) return [{ line_index: 0, matches: [], line: 'Missing <header>', message: '' }]
        if (!content.includes('<footer')) return [{ line_index: 0, matches: [], line: 'Missing <footer>', message: '' }]
    } else if (!content.startsWith('<page')) {
        return [{ line_index: 0, matches: [], line: 'Missing <page> at the beginning of the file', message: '' }]
    }
    return []
}

function analyzeTemplate(filename, content) {
    if (filename.endsWith('.css')) return analyzeCss(content)
    if (filename.endsWith('.hbs')) return analyzeHbs(filename, content)
    return []
}

function renderPageList() {
    const list = document.getElementById('pageList')
    list.innerHTML = ''
    Object.keys(pages).sort().forEach((filename) => {
        const li = document.createElement('li')
        li.className = 'template-page-item' + (filename === currentFilename ? ' active' : '')
        li.dataset.filename = filename

        const label = document.createElement('span')
        label.textContent = filename
        li.appendChild(label)

        const errorCount = pages[filename].result.length
        if (errorCount > 0) {
            const badge = document.createElement('span')
            badge.className = 'error-badge'
            badge.textContent = errorCount
            li.appendChild(badge)
        }

        li.addEventListener('click', () => selectPage(filename))
        list.appendChild(li)
    })
}

function updateErrorBadge(filename) {
    const badge = document.getElementById('errorBadge')
    const count = pages[filename]?.result.length ?? 0
    badge.style.display = count > 0 ? 'inline-block' : 'none'
    badge.textContent = `${count} error${count === 1 ? '' : 's'}`
}

function updateMarkers(filename) {
    if (!monacoEditor) return
    const model = monacoEditor.getModel()
    const markers = (pages[filename]?.result ?? []).map((error) => {
        const lineNumber = error.line_index || 1
        return {
            severity: monaco.MarkerSeverity.Warning,
            startLineNumber: lineNumber,
            startColumn: 1,
            endLineNumber: lineNumber,
            endColumn: (error.line?.length ?? 0) + 1,
            message: error.message ? `${error.message} (${error.matches.join(', ')})` : error.line
        }
    })
    monaco.editor.setModelMarkers(model, 'pentex-lint', markers)
}

function languageForFilename(filename) {
    return filename.endsWith('.css') ? 'css' : 'html'
}

async function loadCss() {
    try {
        const res = await fetch(`/api/templates/${_templateId}/pages/styles.css/raw`)
        if (res.ok) cssContent = await res.text()
    } catch (e) {
        cssContent = ''
    }
    updatePreview()
}

function updatePreview() {
    if (!currentFilename) return
    const frame = document.getElementById('previewFrame')
    const content = monacoEditor ? monacoEditor.getValue() : pages[currentFilename].content
    const headersContent = currentFilename === 'headers.hbs' ? content : (pages['headers.hbs']?.content ?? '')

    let body
    if (currentFilename.endsWith('.css')) {
        body = '<div style="padding:24px;font:14px sans-serif;color:#888">Stylesheet — no page preview.</div>'
    } else if (currentFilename === 'headers.hbs') {
        // Not a <page> itself — a blank one lets zpages.js clone the (possibly
        // unsaved) header/footer being edited into it, same as any real page.
        body = '<page></page>'
    } else {
        try {
            body = Handlebars.compile(content)(SAMPLE_DATA)
        } catch (e) {
            body = `<pre style="color:#b41d1d;padding:16px;white-space:pre-wrap">${String(e).replace(/</g, '&lt;')}</pre>`
        }
    }

    // Use the app's real pagination/header-footer engine (zealtime.js + zpages.js)
    // instead of approximating it — it already handles --z-N token synthesis,
    // header/footer cloning per page (respecting no-header/no-footer), and
    // page-break/overflow splitting exactly like the report editor does.
    frame.srcdoc = `<!doctype html><html><head>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/zalo-alex/zutils@main/lib/zpages.css" crossorigin="anonymous">
        <style>${cssContent}</style>
        <script src="https://cdn.jsdelivr.net/gh/zalo-alex/zutils@main/lib/zprocess.js"></script>
    </head><body>
        <div class="headers-container">${headersContent}</div>
        <pages>${body}</pages>
        <script type="module" src="https://cdn.jsdelivr.net/gh/zalo-alex/zutils@main/lib/zealtime.js"></script>
        <script type="module" src="https://cdn.jsdelivr.net/gh/zalo-alex/zutils@main/lib/zpages.js"></script>
        <script type="module">window.z = { ...window.z, ...${JSON.stringify(SAMPLE_DATA)} }</script>
    </body></html>`
}

function onEditorContentChanged() {
    pages[currentFilename].content = monacoEditor.getValue()
    pages[currentFilename].result = analyzeTemplate(currentFilename, pages[currentFilename].content)
    updateErrorBadge(currentFilename)
    updateMarkers(currentFilename)
    renderPageList()

    clearTimeout(previewTimer)
    previewTimer = setTimeout(updatePreview, 300)
}

function selectPage(filename) {
    if (currentFilename && currentFilename !== filename && isPageDirty(currentFilename)) {
        if (!confirm('You have unsaved changes on this page. Discard them and switch?')) return
    }
    currentFilename = filename
    document.getElementById('currentPageName').textContent = filename
    const saveBtn = document.getElementById('saveBtn')
    if (saveBtn) saveBtn.disabled = false
    renderPageList()
    updateErrorBadge(filename)

    require(['vs/editor/editor.main'], () => {
        if (!monacoEditor) {
            monacoEditor = monaco.editor.create(document.getElementById('monacoContainer'), {
                value: pages[filename].content,
                language: languageForFilename(filename),
                theme: 'vs-dark',
                readOnly: !_isAdmin,
                automaticLayout: true
            })
            monacoEditor.onDidChangeModelContent(onEditorContentChanged)
        } else {
            monacoEditor.setValue(pages[filename].content)
            monaco.editor.setModelLanguage(monacoEditor.getModel(), languageForFilename(filename))
        }
        updateMarkers(filename)
        updatePreview()
    })
}

async function savePage() {
    if (!currentFilename || !monacoEditor) return
    const content = monacoEditor.getValue()
    const res = await fetch(`/api/templates/${_templateId}/pages/${encodeURIComponent(currentFilename)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrfToken() },
        body: JSON.stringify({ content })
    })
    if (!res.ok) {
        alert('Failed to save page.')
        return
    }
    const data = await res.json()
    pages[currentFilename] = { content: data.content, result: data.result, savedContent: data.content }
    updateErrorBadge(currentFilename)
    updateMarkers(currentFilename)
    renderPageList()
}

document.getElementById('saveBtn')?.addEventListener('click', savePage)

let versionsPanelOpen = false

async function fetchVersions() {
    const res = await fetch(`/api/templates/${_templateId}/versions`)
    const versions = res.ok ? await res.json() : []
    renderVersionList(versions)
}

function renderVersionList(versions) {
    const list = document.getElementById('versionList')
    list.innerHTML = ''
    if (versions.length === 0) {
        list.innerHTML = '<li class="version-empty">No versions yet.</li>'
        return
    }
    versions.forEach((v) => {
        const li = document.createElement('li')
        li.className = 'version-item'
        const date = v.created_at ? new Date(v.created_at).toLocaleString() : ''
        li.innerHTML = `
            <div class="version-item-main">
                <span class="version-number">v${v.version_number}</span>
                <span class="version-label">${v.label ? v.label : '—'}</span>
            </div>
            <div class="version-item-meta">${v.created_by_username} · ${date} · ${v.page_count} page${v.page_count === 1 ? '' : 's'}</div>
            <button class="version-download-btn" data-version-id="${v.id}">Download</button>
        `
        li.querySelector('.version-download-btn').addEventListener('click', () => downloadVersion(v.id))
        list.appendChild(li)
    })
}

function downloadVersion(versionId) {
    window.location.href = `/api/templates/${_templateId}/versions/${versionId}/download`
}

function toggleVersionsPanel(forceOpen) {
    const panel = document.getElementById('versionsPanel')
    versionsPanelOpen = forceOpen !== undefined ? forceOpen : !versionsPanelOpen
    panel.hidden = !versionsPanelOpen
    if (versionsPanelOpen) fetchVersions()
}

async function createVersion() {
    const label = prompt('Optional label for this version:', '')
    if (label === null) return
    const res = await fetch(`/api/templates/${_templateId}/versions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrfToken() },
        body: JSON.stringify({ label })
    })
    if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        alert(data.error || 'Failed to create version.')
        return
    }
    toggleVersionsPanel(true)
}

document.getElementById('createVersionBtn')?.addEventListener('click', createVersion)
document.getElementById('versionsBtn')?.addEventListener('click', () => toggleVersionsPanel())
document.getElementById('versionsPanelClose')?.addEventListener('click', () => toggleVersionsPanel(false))

window.addEventListener('beforeunload', (e) => {
    if (!hasUnsavedChanges()) return
    e.preventDefault()
    e.returnValue = ''
})

renderPageList()
loadCss()
