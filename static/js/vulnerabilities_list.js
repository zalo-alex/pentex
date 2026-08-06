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
