import { updateCvssDisplay } from './cvss.js'
import { tinymceConfig } from './src/constants.js'

// TinyMCE for rich text fields
for (const field of ['description', 'remediation']) {
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
