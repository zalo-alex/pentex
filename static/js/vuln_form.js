import { updateCvssDisplay } from './cvss.js'
import { tinymceConfig } from './src/constants.js'

// TinyMCE for rich text fields
for (const field of ['description', 'observation', 'remediation', 'references']) {
    tinymce.init({
        ...tinymceConfig,
        selector: `#${field}`,
        license_key: 'gpl'
    })
}

// CVSS: update hidden inputs whenever a metric button is clicked
const cvssSection = document.querySelector('.cvss-section')

document.addEventListener('click', (e) => {
    const btn = e.target.closest('.metric-buttons button')
    if (!btn || !cvssSection.contains(btn)) return

    btn.closest('.metric-buttons').querySelectorAll('button').forEach(b => b.classList.remove('active'))
    btn.classList.add('active')

    const { score, vector, severity } = updateCvssDisplay(cvssSection)
    document.getElementById('cvss_score').value = score
    document.getElementById('cvss_vector').value = vector
    document.getElementById('severity').value = severity.text
})

// Flush TinyMCE content into textareas before submit
document.querySelector('form').addEventListener('submit', () => {
    tinymce.triggerSave()
})

// Translate dialog
window.openTranslateDialog = async (btn) => {
    const vulnId = btn.dataset.vulnId
    const targetLang = btn.dataset.targetLang
    const force = btn.dataset.force === 'true'

    if (force && !confirm(`Regenerate the ${targetLang} version from this vulnerability's current content? This overwrites its existing translation.`)) {
        return
    }

    document.getElementById('translateDialogTitle').textContent = `Translating to ${targetLang}…`
    document.getElementById('translateStatusText').textContent = 'Contacting translation service…'
    document.getElementById('translateProgressFill').classList.add('progress-fill-indeterminate')
    document.getElementById('translateCloseBtn').style.display = 'none'
    document.getElementById('translateDialog').classList.add('open')

    try {
        const res = await fetch(`/api/vulnerabilities/${vulnId}/translate`, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrfToken(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ force })
        })
        const data = await res.json()
        if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)

        document.getElementById('translateProgressFill').classList.remove('progress-fill-indeterminate')
        document.getElementById('translateProgressFill').style.width = '100%'
        document.getElementById('translateStatusText').textContent = 'Done — opening translation…'
        window.location.href = `/vulnerabilities/${data.id}/edit`
    } catch (err) {
        document.getElementById('translateProgressFill').classList.remove('progress-fill-indeterminate')
        document.getElementById('translateStatusText').textContent = 'Translation failed: ' + err.message
        document.getElementById('translateCloseBtn').style.display = 'inline-block'
    }
}

window.closeTranslateDialog = () => {
    document.getElementById('translateDialog').classList.remove('open')
}
