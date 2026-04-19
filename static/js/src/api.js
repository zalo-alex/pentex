export async function apiGetVulnerabilities() {
    const res = await fetch('/api/vulnerabilities')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
}

function _csrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.content ?? ''
}

export async function apiCreateVulnerability(payload) {
    const res = await fetch('/api/vulnerabilities', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrfToken() },
        body: JSON.stringify(payload)
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
}

export async function apiUpdateVulnerability(id, payload) {
    const res = await fetch(`/api/vulnerabilities/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrfToken() },
        body: JSON.stringify(payload)
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
}

export async function apiGetReport(reportId) {
    const res = await fetch(`/api/reports/${reportId}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
}

export async function apiSaveReport(reportId, content) {
    const res = await fetch(`/api/reports/${reportId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrfToken() },
        body: JSON.stringify({ content })
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
}
