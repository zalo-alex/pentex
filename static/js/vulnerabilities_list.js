async function deleteVulnerability(id, btn) {
    if (!confirm('Delete this vulnerability? This will not affect reports it was already added to.')) return

    const res = await fetch('/api/vulnerabilities/' + id, { method: 'DELETE', headers: { 'X-CSRFToken': csrfToken() } })
    if (res.ok) {
        btn.closest('tr').remove()
        if (!document.querySelector('.list-card tbody tr')) {
            document.querySelector('.list-card').innerHTML = '<p class="empty">No vulnerabilities yet.</p>'
        }
    }
}

function openImportDialog() {
    document.getElementById('importForm').style.display = ''
    document.getElementById('importForm').reset()
    document.getElementById('importProgress').style.display = 'none'
    document.getElementById('importCloseBtn').style.display = 'none'
    document.getElementById('importDialog')?.classList.add('open')
}
function closeImportDialog() {
    document.getElementById('importDialog')?.classList.remove('open')
}
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeImportDialog()
})

function setImportProgress(pct, text, counts) {
    document.getElementById('importProgressFill').style.width = pct + '%'
    document.getElementById('importProgressText').textContent = text
    if (counts !== undefined) document.getElementById('importProgressCounts').textContent = counts
}

function startImport(event) {
    event.preventDefault()

    const fileInput = document.getElementById('importFile')
    if (!fileInput.files.length) return false

    const formData = new FormData()
    formData.append('file', fileInput.files[0])

    document.getElementById('importForm').style.display = 'none'
    document.getElementById('importProgress').style.display = 'block'
    setImportProgress(0, 'Uploading and parsing file…', '')

    fetch('/vulnerabilities/import', { method: 'POST', body: formData, headers: { 'X-CSRFToken': csrfToken() } })
        .then(async (res) => {
            const body = await res.json()
            if (!res.ok) throw new Error(body.error || 'Import failed to start.')
            pollImportStatus(body.job_id)
        })
        .catch((err) => {
            setImportProgress(0, err.message, '')
            document.getElementById('importCloseBtn').style.display = 'inline-block'
        })

    return false
}

async function pollImportStatus(jobId) {
    let res
    try {
        res = await fetch('/vulnerabilities/import/' + jobId + '/status')
    } catch {
        setTimeout(() => pollImportStatus(jobId), 1000)
        return
    }
    if (!res.ok) return

    const job = await res.json()
    const pct = job.total ? Math.round((job.processed / job.total) * 100) : 0
    setImportProgress(pct, job.message || ('Processed ' + job.processed + ' / ' + job.total + '…'),
        job.created + ' created · ' + job.translated + ' translated · ' + job.failed + ' failed')

    if (job.status === 'running') {
        setTimeout(() => pollImportStatus(jobId), 700)
    } else {
        document.getElementById('importCloseBtn').style.display = 'inline-block'
    }
}
