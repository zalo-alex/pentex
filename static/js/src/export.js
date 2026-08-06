import { renderPages } from "./render.js"
import { apiExportPdf } from "./api.js"

window.exportTemplateHtml = null;
fetchExportTemplate()

async function fetchExportTemplate() {
    const staticFetch = async (path) => await (await fetch(path, { cache: 'no-store' })).text()
    exportTemplateHtml = `<html>
        <head>
            <script>${await staticFetch("https://cdn.jsdelivr.net/gh/zalo-alex/zutils/lib/zprocess.js")}</script>
            <style>${await staticFetch("https://cdn.jsdelivr.net/gh/zalo-alex/zutils/lib/zpages.css")}</style>
            <style>${await staticFetch(`/api/templates/${_activeTemplateId}/pages/styles.css/raw`)}</style>
        </head>
        <body>
            {{EXPORTED_HTML}}
            <script>zpagesFreeze = true;</script>
            <script type="module">${await staticFetch("https://cdn.jsdelivr.net/gh/zalo-alex/zutils/lib/zealtime.js")}</script>
            <script type="module">${await staticFetch("https://cdn.jsdelivr.net/gh/zalo-alex/zutils/lib/zpages.js")}</script>
        </body>
    </html>`
}         

async function sleep(ms) {
    return new Promise((resolve) => {
        setTimeout(() => resolve(), ms)
    })
}

async function convertImagesToBase64(html) {
    const parser = new DOMParser()
    const doc = parser.parseFromString(html, 'text/html')
    const imgs = doc.querySelectorAll('img[src]')
    await Promise.all([...imgs].map(async (img) => {
        if (img.src.startsWith('data:')) return
        try {
            const resp = await fetch(img.src)
            const blob = await resp.blob()
            const dataUrl = await new Promise((resolve) => {
                const reader = new FileReader()
                reader.onloadend = () => resolve(reader.result)
                reader.readAsDataURL(blob)
            })
            img.src = dataUrl
        } catch (e) {
            console.warn('Failed to convert image to base64:', img.src, e)
        }
    }))
    return doc.documentElement.outerHTML
}

window.compileHtml = async () => {
    renderPages()
    await sleep(1000)
    document.querySelectorAll('[z-template="rawEditButton"]').forEach(btn => btn.remove())
    const pagesHtml = document.querySelector("pages").outerHTML
    const exportedHtml = document.querySelector(".headers-container").outerHTML + pagesHtml
    const rawHtml = exportTemplateHtml.replace("{{EXPORTED_HTML}}", exportedHtml)
    return await convertImagesToBase64(rawHtml)
}

window.exportHtml = async () => {
    const html = await compileHtml();
    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'export.html';
    a.click();
    URL.revokeObjectURL(url);
}

window.exportPdf = async () => {
    const reportMatch = window.location.pathname.match(/^\/reports\/([^/]+)$/)
    const reportId = reportMatch ? reportMatch[1] : null
    if (!reportId) throw new Error('No report ID in URL')

    const html = await compileHtml();
    const blob = await apiExportPdf(reportId, html);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'export.pdf';
    a.click();
    URL.revokeObjectURL(url);
}