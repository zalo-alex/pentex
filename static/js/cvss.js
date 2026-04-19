export const cvssWeights = {
    AV: { N: 0.85, A: 0.62, L: 0.55, P: 0.2 },
    AC: { L: 0.77, H: 0.44 },
    PR: { U: { N: 0.85, L: 0.62, H: 0.27 }, C: { N: 0.85, L: 0.68, H: 0.5 } },
    UI: { N: 0.85, R: 0.62 },
    C: { N: 0, L: 0.22, H: 0.56 },
    I: { N: 0, L: 0.22, H: 0.56 },
    A: { N: 0, L: 0.22, H: 0.56 }
}

export const cvssImpactMap = {
    'N': { text: 'None', level: 'none' },
    'L': { text: 'Low', level: 'low' },
    'H': { text: 'High', level: 'high' }
}

export function calculateCVSS(metrics) {
    const iss = 1 - ((1 - cvssWeights.C[metrics.C]) * (1 - cvssWeights.I[metrics.I]) * (1 - cvssWeights.A[metrics.A]))

    let impact
    if (metrics.S === 'U') {
        impact = 6.42 * iss
    } else {
        impact = 7.52 * (iss - 0.029) - 3.25 * Math.pow(iss - 0.02, 15)
    }

    const prWeight = cvssWeights.PR[metrics.S][metrics.PR]
    const exploitability = 8.22 * cvssWeights.AV[metrics.AV] * cvssWeights.AC[metrics.AC] * prWeight * cvssWeights.UI[metrics.UI]

    if (impact <= 0) return 0

    let score
    if (metrics.S === 'U') {
        score = Math.min(impact + exploitability, 10)
    } else {
        score = Math.min(1.08 * (impact + exploitability), 10)
    }

    return Math.ceil(score * 10) / 10
}

export function getCvssVector(metrics) {
    return `CVSS:3.1/AV:${metrics.AV}/AC:${metrics.AC}/PR:${metrics.PR}/UI:${metrics.UI}/S:${metrics.S}/C:${metrics.C}/I:${metrics.I}/A:${metrics.A}`
}

export function getCvssSeverity(score) {
    if (score === 0) return { text: 'NONE', level: 'none' }
    if (score < 4) return { text: 'LOW', level: 'low' }
    if (score < 7) return { text: 'MEDIUM', level: 'medium' }
    if (score < 9) return { text: 'HIGH', level: 'high' }
    return { text: 'CRITICAL', level: 'critical' }
}

export function getMetricsFromSection(section) {
    const metrics = { AV: 'N', AC: 'L', PR: 'N', UI: 'N', S: 'U', C: 'N', I: 'N', A: 'N' }
    section.querySelectorAll('.metric-buttons').forEach(group => {
        const metric = group.dataset.metric
        const active = group.querySelector('.active')
        if (active) metrics[metric] = active.dataset.value
    })
    return metrics
}

// Updates the DOM display in a .cvss-section and returns the computed values.
export function updateCvssDisplay(section) {
    const metrics = getMetricsFromSection(section)
    const score = calculateCVSS(metrics)
    const vector = getCvssVector(metrics)
    const severity = getCvssSeverity(score)

    section.querySelector('.cvss-score').textContent = score.toFixed(1)
    section.querySelector('.cvss-severity').textContent = severity.text
    section.querySelector('.cvss-severity').dataset.severity = severity.level
    section.querySelector('.cvss-vector').textContent = vector

    return { score, vector, severity, metrics }
}
