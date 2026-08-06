function openNewReportDialog() {
    document.getElementById('newReportDialog').classList.add('open')
    const input = document.getElementById('newReportName')
    input.value = ''
    setTimeout(() => input.focus(), 50)
}

function closeNewReportDialog() {
    document.getElementById('newReportDialog').classList.remove('open')
}

const newReportNameInput = document.getElementById('newReportName')
if (newReportNameInput) {
    newReportNameInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') createReport()
        if (e.key === 'Escape') closeNewReportDialog()
    })
}

async function createReport() {
    const name = document.getElementById('newReportName').value.trim()
    if (!name) return
    const category_id = document.getElementById('newReportCategory').value || null

    const res = await fetch('/api/reports', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
        body: JSON.stringify({ name, category_id })
    })

    if (!res.ok) return
    const data = await res.json()
    window.location.href = '/reports/' + data.id
}

async function deleteReport(id, btn) {
    if (!confirm('Delete this report?')) return

    const res = await fetch('/api/reports/' + id, { method: 'DELETE', headers: { 'X-CSRFToken': csrfToken() } })
    if (res.ok) {
        btn.closest('tr').remove()
        if (!document.querySelector('.list-card tbody tr')) {
            document.querySelector('.list-card').innerHTML = '<p class="empty">No reports yet.</p>'
        }
    }
}
