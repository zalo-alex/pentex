function openNewReportDialog() {
    document.getElementById('newReportDialog').classList.add('open')
    const input = document.getElementById('newReportName')
    input.value = ''
    setTimeout(() => input.focus(), 50)
}

function closeNewReportDialog() {
    document.getElementById('newReportDialog').classList.remove('open')
}

async function createReport() {
    const name = document.getElementById('newReportName').value.trim()
    if (!name) return

    const res = await fetch('/api/reports', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
        body: JSON.stringify({ name })
    })

    if (!res.ok) return
    const data = await res.json()
    window.location.href = '/reports/' + data.id
}
