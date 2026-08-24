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

const PINNED_FILENAMES = new Set(['headers.hbs', 'styles.css'])

let pageOrder = _initialPages.map(p => p.filename).filter(f => !PINNED_FILENAMES.has(f))
let pinnedOrder = _initialPages.map(p => p.filename).filter(f => PINNED_FILENAMES.has(f))
let draggedFilename = null
let draggedEl = null
let placeholderEl = null

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

function buildPageItem(filename, draggable) {
    const li = document.createElement('li')
    li.className = 'template-page-item' + (filename === currentFilename ? ' active' : '')
    li.dataset.filename = filename
    li.draggable = draggable

    if (draggable) {
        const handle = document.createElement('span')
        handle.className = 'drag-handle'
        handle.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="12" height="12"><circle cx="8" cy="5" r="1.6"/><circle cx="16" cy="5" r="1.6"/><circle cx="8" cy="12" r="1.6"/><circle cx="16" cy="12" r="1.6"/><circle cx="8" cy="19" r="1.6"/><circle cx="16" cy="19" r="1.6"/></svg>'
        li.appendChild(handle)
    }

    const label = document.createElement('span')
    label.textContent = filename
    label.className = 'template-page-item-label'
    li.appendChild(label)

    const errorCount = pages[filename].result.length
    if (errorCount > 0) {
        const badge = document.createElement('span')
        badge.className = 'error-badge'
        badge.textContent = errorCount
        li.appendChild(badge)
    }

    li.addEventListener('click', () => selectPage(filename))
    return li
}

function renderPageList() {
    const list = document.getElementById('pageList')
    list.innerHTML = ''
    pageOrder.forEach((filename) => list.appendChild(buildPageItem(filename, _isAdmin)))
}

function renderPinnedList() {
    const list = document.getElementById('pinnedPageList')
    list.innerHTML = ''
    pinnedOrder.forEach((filename) => list.appendChild(buildPageItem(filename, false)))
    document.getElementById('pinnedListDivider').style.display = pinnedOrder.length ? '' : 'none'
}

function renderLists() {
    renderPageList()
    renderPinnedList()
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

function updateSaveButtonState() {
    const saveBtn = document.getElementById('saveBtn')
    if (!saveBtn || !currentFilename) return
    // Don't clobber the transient "Saving…" / "Saved" / "Save failed" states — they clear themselves.
    if (saveBtn.classList.contains('saving') || saveBtn.classList.contains('saved') || saveBtn.classList.contains('save-error')) return
    saveBtn.textContent = 'Save'
    saveBtn.disabled = !isPageDirty(currentFilename)
}

function onEditorContentChanged() {
    pages[currentFilename].content = monacoEditor.getValue()
    pages[currentFilename].result = analyzeTemplate(currentFilename, pages[currentFilename].content)
    updateErrorBadge(currentFilename)
    updateMarkers(currentFilename)
    renderLists()
    updateSaveButtonState()

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
    if (saveBtn) saveBtn.classList.remove('saving', 'saved', 'save-error')
    updateSaveButtonState()
    renderLists()
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
    const savingFilename = currentFilename
    const content = monacoEditor.getValue()
    const saveBtn = document.getElementById('saveBtn')

    if (saveBtn) {
        saveBtn.classList.remove('saved', 'save-error')
        saveBtn.classList.add('saving')
        saveBtn.disabled = true
        saveBtn.textContent = 'Saving…'
    }

    let res, networkError
    try {
        res = await fetch(`/api/templates/${_templateId}/pages/${encodeURIComponent(currentFilename)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrfToken() },
            body: JSON.stringify({ content })
        })
    } catch (e) {
        networkError = e
    }

    // The user may have switched pages while the request was in flight — only touch the
    // button if we're still looking at the page that was actually saved.
    const stillOnSamePage = currentFilename === savingFilename

    if (networkError || !res.ok) {
        if (saveBtn && stillOnSamePage) {
            saveBtn.classList.remove('saving')
            saveBtn.classList.add('save-error')
            saveBtn.disabled = false
            saveBtn.textContent = 'Save failed'
            setTimeout(() => {
                saveBtn.classList.remove('save-error')
                updateSaveButtonState()
            }, 2200)
        }
        return
    }

    const data = await res.json()
    pages[savingFilename] = { content: data.content, result: data.result, savedContent: data.content }

    if (stillOnSamePage) {
        updateErrorBadge(savingFilename)
        updateMarkers(savingFilename)
    }
    renderLists()

    if (saveBtn && stillOnSamePage) {
        saveBtn.classList.remove('saving')
        saveBtn.classList.add('saved')
        saveBtn.disabled = true
        saveBtn.textContent = 'Saved ✓'
        setTimeout(() => {
            saveBtn.classList.remove('saved')
            updateSaveButtonState()
        }, 1400)
    }
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
    if (versionsPanelOpen) {
        toggleRulesPanel(false)
        fetchVersions()
    }
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

let rulesPanelOpen = false

async function fetchRules() {
    const res = await fetch('/api/translation-rules')
    const rules = res.ok ? await res.json() : []
    renderRuleList(rules)
}

function renderRuleList(rules) {
    const list = document.getElementById('ruleList')
    list.innerHTML = ''
    if (rules.length === 0) {
        list.innerHTML = '<li class="rule-empty">No translation rules yet.</li>'
        return
    }
    rules.forEach((r) => {
        const li = document.createElement('li')
        li.className = 'rule-item'
        const date = r.created_at ? new Date(r.created_at).toLocaleString() : ''
        li.innerHTML = `
            <div>
                <div class="rule-item-text"></div>
                <div class="rule-item-meta">${r.source === 'auto' ? 'Auto-suggested' : 'Manual'} · ${r.created_by_username} · ${date}</div>
            </div>
            <button class="btn-delete" title="Delete">×</button>
        `
        li.querySelector('.rule-item-text').textContent = r.text
        li.querySelector('.btn-delete').addEventListener('click', () => deleteRule(r.id))
        list.appendChild(li)
    })
}

async function addRule() {
    const textarea = document.getElementById('newRuleText')
    const text = textarea.value.trim()
    if (!text) return
    const res = await fetch('/api/translation-rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrfToken() },
        body: JSON.stringify({ text })
    })
    if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        alert(data.error || 'Failed to add rule.')
        return
    }
    textarea.value = ''
    fetchRules()
}

async function deleteRule(ruleId) {
    if (!confirm('Delete this translation rule?')) return
    const res = await fetch(`/api/translation-rules/${ruleId}`, {
        method: 'DELETE', headers: { 'X-CSRFToken': _csrfToken() }
    })
    if (res.ok) fetchRules()
}

function toggleRulesPanel(forceOpen) {
    const panel = document.getElementById('rulesPanel')
    if (!panel) return
    rulesPanelOpen = forceOpen !== undefined ? forceOpen : !rulesPanelOpen
    panel.hidden = !rulesPanelOpen
    if (rulesPanelOpen) {
        toggleVersionsPanel(false)
        fetchRules()
    }
}

document.getElementById('addRuleBtn')?.addEventListener('click', addRule)
document.getElementById('rulesBtn')?.addEventListener('click', () => toggleRulesPanel())
document.getElementById('rulesPanelClose')?.addEventListener('click', () => toggleRulesPanel(false))

function setTemplateTranslateProgress(pct, text, counts) {
    document.getElementById('templateTranslateProgressFill').style.width = pct + '%'
    document.getElementById('templateTranslateStatusText').textContent = text
    if (counts !== undefined) document.getElementById('templateTranslateCounts').textContent = counts
}

window.closeTemplateTranslateDialog = () => {
    document.getElementById('templateTranslateDialog').classList.remove('open')
}

async function pollTemplateTranslateStatus(jobId) {
    let res
    try {
        res = await fetch(`/templates/${_templateId}/translate/${jobId}/status`)
    } catch {
        setTimeout(() => pollTemplateTranslateStatus(jobId), 1000)
        return
    }
    if (!res.ok) return

    const job = await res.json()
    const pct = job.total ? Math.round((job.processed / job.total) * 100) : 0
    setTemplateTranslateProgress(pct, job.message || `Processed ${job.processed} / ${job.total}…`,
        job.total ? `${job.processed} / ${job.total} pages translated` : '')

    if (job.status === 'running') {
        setTimeout(() => pollTemplateTranslateStatus(jobId), 700)
    } else if (job.status === 'done') {
        setTemplateTranslateProgress(100, job.message, '')
        window.location.href = job.redirect
    } else {
        document.getElementById('templateTranslateCloseBtn').style.display = 'inline-block'
    }
}

function openTranslateReviewDialog(changes, pagesWithoutBaseline) {
    return new Promise((resolve) => {
        const list = document.getElementById('translateChangesList')
        const intro = document.getElementById('translateChangesIntro')
        const warning = document.getElementById('translateChangesWarning')

        intro.style.display = changes.length ? '' : 'none'
        list.style.display = changes.length ? '' : 'none'
        if (pagesWithoutBaseline && pagesWithoutBaseline.length) {
            document.getElementById('translateChangesWarningPages').textContent = pagesWithoutBaseline.join(', ')
            warning.style.display = ''
        } else {
            warning.style.display = 'none'
        }

        list.innerHTML = ''
        changes.forEach((c, idx) => {
            const li = document.createElement('li')
            li.className = 'rule-checklist-item'

            const checkbox = document.createElement('input')
            checkbox.type = 'checkbox'
            checkbox.checked = true
            checkbox.dataset.idx = String(idx)

            const body = document.createElement('div')
            const filenameEl = document.createElement('span')
            filenameEl.className = 'rule-checklist-filename'
            filenameEl.textContent = c.filename
            const diffEl = document.createElement('div')
            diffEl.className = 'rule-checklist-diff'
            if (c.old) {
                const del = document.createElement('del')
                del.textContent = c.old
                diffEl.appendChild(del)
                diffEl.appendChild(document.createTextNode(' '))
            }
            if (c.new) {
                const ins = document.createElement('ins')
                ins.textContent = c.new
                diffEl.appendChild(ins)
            }
            body.appendChild(filenameEl)
            body.appendChild(diffEl)

            li.appendChild(checkbox)
            li.appendChild(body)
            list.appendChild(li)
        })

        const dialog = document.getElementById('translateChangesDialog')
        const continueBtn = document.getElementById('translateChangesContinueBtn')
        const cancelBtn = document.getElementById('translateChangesCancelBtn')

        const cleanup = () => {
            dialog.classList.remove('open')
            continueBtn.removeEventListener('click', onContinue)
            cancelBtn.removeEventListener('click', onCancel)
        }
        const onContinue = () => {
            const checked = [...list.querySelectorAll('input[type="checkbox"]:checked')]
                .map((cb) => changes[Number(cb.dataset.idx)])
            cleanup()
            resolve(checked)
        }
        const onCancel = () => {
            cleanup()
            resolve(null)
        }
        continueBtn.addEventListener('click', onContinue)
        cancelBtn.addEventListener('click', onCancel)

        dialog.classList.add('open')
    })
}

window.openTemplateTranslateDialog = async (btn) => {
    const targetLang = btn.dataset.targetLang
    const force = btn.dataset.force === 'true'
    let approvedChanges = []

    if (force) {
        const targetName = btn.dataset.targetName || `the ${targetLang} version`
        const plainConfirm = () => confirm(
            `Regenerate "${targetName}" from this template's current content?\n\n` +
            `Its existing content will be saved as a version first, so you can restore it from the Versions panel if needed.`
        )

        let preview = null
        try {
            const previewRes = await fetch(`/templates/${_templateId}/translate/preview-changes`)
            if (previewRes.ok) preview = await previewRes.json()
        } catch (e) {
            // Preview failing shouldn't block re-translation itself — fall through to the plain confirm below.
        }

        const changes = (preview && preview.changes) || []
        const pagesWithoutBaseline = (preview && preview.pages_without_baseline) || []

        if (changes.length || pagesWithoutBaseline.length) {
            const approved = await openTranslateReviewDialog(changes, pagesWithoutBaseline)
            if (approved === null) return  // user cancelled the review step
            approvedChanges = approved
        } else if (!plainConfirm()) {
            return
        }
    }

    document.getElementById('templateTranslateDialogTitle').textContent = force
        ? `Re-translating to ${targetLang}…` : `Translating to ${targetLang}…`
    document.getElementById('templateTranslateCloseBtn').style.display = 'none'
    setTemplateTranslateProgress(0, 'Starting translation…', '')
    document.getElementById('templateTranslateDialog').classList.add('open')

    try {
        const res = await fetch(`/templates/${_templateId}/translate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrfToken() },
            body: JSON.stringify({ force, approved_changes: approvedChanges })
        })
        const data = await res.json()
        if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)

        if (data.done) {
            setTemplateTranslateProgress(100, 'Already translated — opening it…', '')
            window.location.href = data.redirect
            return
        }
        pollTemplateTranslateStatus(data.job_id)
    } catch (err) {
        setTemplateTranslateProgress(0, 'Translation failed: ' + err.message, '')
        document.getElementById('templateTranslateCloseBtn').style.display = 'inline-block'
    }
}

window.addEventListener('beforeunload', (e) => {
    if (!hasUnsavedChanges()) return
    e.preventDefault()
    e.returnValue = ''
})

function closestPageItem(target) {
    return target.closest('.template-page-item')
}

function createPlaceholder() {
    const li = document.createElement('li')
    li.className = 'template-page-item drag-placeholder'
    return li
}

function visibleItems(list) {
    return Array.from(list.children).filter(el => el !== draggedEl)
}

function capturePositions(list) {
    const positions = new Map()
    visibleItems(list).forEach((el) => positions.set(el, el.getBoundingClientRect().top))
    return positions
}

function animateFromPositions(list, previousPositions) {
    visibleItems(list).forEach((el) => {
        const before = previousPositions.get(el)
        if (before == null) return
        const after = el.getBoundingClientRect().top
        const delta = before - after
        if (!delta) return
        el.style.transition = 'none'
        el.style.transform = `translateY(${delta}px)`
        requestAnimationFrame(() => {
            el.style.transition = 'transform 160ms ease'
            el.style.transform = ''
        })
        el.addEventListener('transitionend', () => { el.style.transition = '' }, { once: true })
    })
}

async function savePageOrder(previousOrder) {
    const res = await fetch(`/api/templates/${_templateId}/pages/order`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrfToken() },
        body: JSON.stringify({ order: pageOrder })
    })
    if (!res.ok) {
        alert('Failed to save the new page order.')
        pageOrder = previousOrder
        renderPageList()
    }
}

if (_isAdmin) {
    const list = document.getElementById('pageList')

    list.addEventListener('dragstart', (e) => {
        const li = closestPageItem(e.target)
        if (!li) return
        draggedFilename = li.dataset.filename
        draggedEl = li
        e.dataTransfer.effectAllowed = 'move'
        e.dataTransfer.setData('text/plain', draggedFilename) // Firefox requires data to allow the drag

        placeholderEl = createPlaceholder()
        li.parentNode.insertBefore(placeholderEl, li.nextSibling)
        // Defer hiding so the browser captures the native drag-ghost image first
        setTimeout(() => li.classList.add('drag-source-hidden'), 0)
    })

    list.addEventListener('dragover', (e) => {
        if (!draggedFilename || !placeholderEl) return
        e.preventDefault()
        e.dataTransfer.dropEffect = 'move'

        const li = closestPageItem(e.target)
        if (!li || li === placeholderEl) return

        const before = (e.clientY - li.getBoundingClientRect().top) < li.offsetHeight / 2
        const target = before ? li : li.nextSibling
        if (placeholderEl.nextSibling === target) return

        const previousPositions = capturePositions(list)
        list.insertBefore(placeholderEl, target)
        animateFromPositions(list, previousPositions)
    })

    function finishDrag(commit) {
        if (!draggedFilename) return
        if (commit && placeholderEl) {
            const newOrder = Array.from(list.children)
                .filter(el => el !== draggedEl)
                .map(el => el === placeholderEl ? draggedFilename : el.dataset.filename)
            const previousOrder = pageOrder.slice()
            const changed = newOrder.join(' ') !== pageOrder.join(' ')
            pageOrder = newOrder
            draggedFilename = null
            draggedEl = null
            placeholderEl = null
            renderPageList()
            if (changed) savePageOrder(previousOrder)
            return
        }
        draggedFilename = null
        draggedEl = null
        placeholderEl = null
        renderPageList()
    }

    list.addEventListener('drop', (e) => {
        e.preventDefault()
        finishDrag(true)
    })

    list.addEventListener('dragend', (e) => {
        finishDrag(e.dataTransfer.dropEffect === 'move')
    })
}

renderLists()
loadCss()
