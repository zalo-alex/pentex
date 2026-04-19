import { renderPages } from "./src/render.js";
import { preloadTemplates, templateCache, updateTemplate } from "./src/templates.js";
import { tinymceConfig } from "./src/constants.js"
import { downloadSaveFile, importSaveFile, initBinds, pagesCount, saveLocal, zidIndexes, saveToServer, loadFromServer } from "./src/store.js";
import { apiGetVulnerabilities, apiCreateVulnerability, apiUpdateVulnerability, apiGetReport } from "./src/api.js";
import "./src/export.js"
import "./src/editor.js"
import { updateCvssDisplay as updateCvssDOM, cvssImpactMap } from "./cvss.js"
import { initCollab, emitPageChange, emitFieldFocus, emitFieldBlur, emitFieldChange } from "./collab.js"

window.zidToPage = {}

const buttons = document.querySelectorAll('.nav .button');
const pages = document.querySelectorAll('.sidebar .page');

const _pageNames = ['general', 'executive', 'traces', 'discovery', 'observations', 'findings', 'project'];

// Navbar
buttons.forEach((button, index) => {
    button.addEventListener('click', () => {
        buttons.forEach(btn => btn.classList.remove('active'));
        button.classList.add('active');
        pages.forEach(page => page.style.display = 'none');
        pages[index].style.display = 'block';
        emitPageChange(_pageNames[index]);
    });
});

let renderTimeout = null
let isLoading = false
window.updateData = (callback) => {
    callback()

    if (!isLoading) {
        const navSaveBtn = document.getElementById('navSaveBtn')
        if (navSaveBtn && reportId) navSaveBtn.style.display = ''
    }

    if (renderTimeout) clearTimeout(renderTimeout)
    renderTimeout = setTimeout(() => {
        renderPages()
        renderTimeout = null
    }, 300)
}

window.findingOrder = []
window.tabToFinding = {}


function initTinyMCE(zid, initialContent = {}) {
    const selectors = [`#desc-${zid}`, `#remed-${zid}`, `#poc-${zid}`]
    const fields = ['description', 'remediation', 'poc']

    selectors.forEach((selector, index) => {
        tinymce.init({
            ...tinymceConfig,
            selector: selector,
            images_upload_handler: (blobInfo, progress) => new Promise((resolve, reject) => {
                const base64 = blobInfo.base64();
                resolve('data:' + blobInfo.blob().type + ';base64,' + base64);
            }),
            setup: (editor) => {
                editor.on('init', () => {
                    if (initialContent[fields[index]]) {
                        editor.setContent(initialContent[fields[index]])
                        editor.fire('change')
                    }
                })
                editor.on('change keyup', () => {
                    updateData(() => {
                        const idx = zidIndexes["pages.findings"].indexOf(zid)
                        const content = DOMPurify.sanitize(editor.getContent())
                        window.dataStore.pages.findings[idx][fields[index]] = content
                        saveLocal()
                        emitFieldChange('tinymce', `finding.${idx}.${fields[index]}`, content)
                    })
                })
                editor.on('focus', () => {
                    const idx = zidIndexes["pages.findings"].indexOf(zid)
                    if (idx >= 0) emitFieldFocus(`finding.${idx}.${fields[index]}`)
                })
                editor.on('blur', () => {
                    const idx = zidIndexes["pages.findings"].indexOf(zid)
                    if (idx >= 0) emitFieldBlur(`finding.${idx}.${fields[index]}`)
                })

                editor.on('PastePostProcess', function (e) {
                    // Wait for the content to be pasted
                    setTimeout(async () => {
                        const editorBody = editor.getBody();
                        const images = editorBody.querySelectorAll('img[src^="http"]');

                        const imagePromises = Array.from(images).map(async (img) => {
                            const src = img.getAttribute('src');

                            try {
                                const response = await fetch(src);

                                if (!response.ok) {
                                    throw new Error('Network response was not ok');
                                }

                                const blob = await response.blob();

                                const base64 = await new Promise((resolve, reject) => {
                                    const reader = new FileReader();
                                    reader.onloadend = () => resolve(reader.result);
                                    reader.onerror = reject;
                                    reader.readAsDataURL(blob);
                                });

                                const newImg = document.createElement('img');
                                newImg.src = base64;
                                newImg.style.width = "70%" // Make it that it's the same inside the editor and the page

                                img.parentNode.replaceChild(newImg, img);

                            } catch (err) {
                                const errorSpan = document.createElement('span');
                                errorSpan.textContent = "Couldn't fetch the image";
                                errorSpan.style.color = 'red';
                                errorSpan.style.fontWeight = 'bold';
                                errorSpan.style.border = '2px solid red';
                                errorSpan.style.padding = '4px 8px';
                                errorSpan.style.display = 'inline-block';
                                errorSpan.contentEditable = 'false';

                                // Add a space after to prevent style inheritance
                                const space = document.createTextNode(' ');

                                const parent = img.parentNode;
                                parent.replaceChild(errorSpan, img);
                                parent.insertBefore(space, errorSpan.nextSibling);
                            }
                        });

                        await Promise.all(imagePromises);

                        // Trigger change event to save the updated content
                        editor.fire('change');
                    }, 100);
                });
            },
            license_key: 'gpl'
        })
    })
}

function destroyTinyMCE(zid) {
    const selectors = [`desc-${zid}`, `remed-${zid}`, `poc-${zid}`]
    selectors.forEach(id => {
        const editor = tinymce.get(id)
        if (editor) editor.remove()
    })
}

window.addFinding = (addDefaults = true, initialContent = {}) => {
    let finding = z.create("finding")
    let zid = finding.getAttribute("zid")
    if (addDefaults) {
        pagesCount["findings"]++
        window.dataStore.pages.findings.push({
            name: "",
            description: "",
            remediation: "",
            poc: "",
            cvss: 0.0,
            cvssString: "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N",
            cvssObj: { AV: 'N', AC: 'L', PR: 'N', UI: 'N', S: 'U', C: 'N', I: 'N', A: 'N' },
            severity: "NONE",
            severityLevel: "none",
            cvssImpactText: { C: 'None', I: 'None', A: 'None' },
            cvssImpactLevel: { C: 'none', I: 'none', A: 'none' },
            vulnId: null
        })
    }

    let tab = z.create("finding-tab")
    let tabZid = tab.getAttribute("zid")
    tabToFinding[tabZid] = zid
    z[tabZid].name = initialContent.name || `Unnamed Finding`

    zidIndexes["pages.findings"].push(zid)

    initBinds(finding)

    initTinyMCE(zid, initialContent)

    switchFinding(tabZid)
    renderPages()

    return finding
}

window.removeFinding = (zid) => {
    if (!confirm(`Delete "${z[zid].name}"?`)) return

    let findingZid = tabToFinding[zid]
    let pageId = zidToPage[findingZid]

    // Destroy TinyMCE instances for this finding
    destroyTinyMCE(findingZid)

    delete window.dataStore.pages[pageId]
    delete zidToPage[findingZid]
    findingOrder = findingOrder.filter(id => id !== findingZid)
    pagesCount["findings"]--

    z.delete(findingZid)
    z.delete(zid)
    delete tabToFinding[zid]

    if (findingOrder.length > 0) {
        let lastTabZid = Object.keys(tabToFinding).find(key => tabToFinding[key] === findingOrder[findingOrder.length - 1])
        if (lastTabZid) switchFinding(lastTabZid)
    }
    renderPages()
}

window.switchFinding = (zid) => {
    document.querySelectorAll('.finding').forEach(f => f.style.display = 'none')
    document.querySelectorAll('.finding-tab').forEach(t => t.classList.remove('active'))

    const finding = document.querySelector(`.finding[zid="${tabToFinding[zid]}"]`)
    const tab = document.querySelector(`.finding-tab[zid="${zid}"]`)

    if (finding) finding.style.display = 'block'
    if (tab) tab.classList.add('active')
}

window.updateFindingName = (value, zid) => {
    z[Object.keys(tabToFinding).find(key => tabToFinding[key] === zid)].name = value
}

function updateCvssDisplay(section) {
    const findingZid = section.dataset.finding
    const { score, vector, severity, metrics } = updateCvssDOM(section)

    updateData(() => {
        const findingIndex = zidIndexes["pages.findings"].indexOf(findingZid)
        window.dataStore.pages.findings[findingIndex].cvss = score
        window.dataStore.pages.findings[findingIndex].cvssString = vector
        window.dataStore.pages.findings[findingIndex].cvssObj = metrics
        window.dataStore.pages.findings[findingIndex].severity = severity.text
        window.dataStore.pages.findings[findingIndex].severityLevel = severity.level
        window.dataStore.pages.findings[findingIndex].cvssImpactText = {
            C: cvssImpactMap[metrics.C]?.text || 'None',
            I: cvssImpactMap[metrics.I]?.text || 'None',
            A: cvssImpactMap[metrics.A]?.text || 'None'
        }
        window.dataStore.pages.findings[findingIndex].cvssImpactLevel = {
            C: cvssImpactMap[metrics.C]?.level || 'none',
            I: cvssImpactMap[metrics.I]?.level || 'none',
            A: cvssImpactMap[metrics.A]?.level || 'none'
        }
        saveLocal()
    })
}

function showRawEditPage(origin) {
    let templateId = origin.closest("page").getAttribute("template-id")

    require(['vs/editor/editor.main'], function () {
        const editor = monaco.editor.create(
            document.getElementById('editor'),
            {
                value: templateCache[templateId],
                language: 'html',
                theme: 'vs-dark',
                automaticLayout: true
            }
        );

        window.onRawEditCloseClicked = () => {
            editor.dispose();
            document.querySelector('.raw-edit-dialog-container').style.display = "none"
            renderPages()
        }

        editor.onDidChangeModelContent(() => {
            updateTemplate(templateId, editor.getValue());
        });

        document.querySelector('.raw-edit-dialog-container').style.display = "flex"
    });
}

function escapeHtml(text) {
    const div = document.createElement('div')
    div.textContent = text
    return div.innerHTML
}

function parseCvssVector(vector) {
    const m = { AV: 'N', AC: 'L', PR: 'N', UI: 'N', S: 'U', C: 'N', I: 'N', A: 'N' }
    if (vector) {
        vector.split('/').slice(1).forEach(part => {
            const [k, v] = part.split(':')
            if (k && v) m[k] = v
        })
    }
    return m
}

window.openAddFindingDialog = async () => {
    const container = document.getElementById('addFindingDialog')
    const list = document.getElementById('addFindingDialogList')
    const searchInput = document.getElementById('addFindingSearch')
    
    if (searchInput) searchInput.value = ''
    list.innerHTML = '<p class="vuln-picker-loading">Loading…</p>'
    container.classList.add('open')

    try {
        const vulns = await apiGetVulnerabilities()

        list.innerHTML = ''

        const emptyItem = document.createElement('div')
        emptyItem.className = 'vuln-picker-item'
        emptyItem.innerHTML = '<span class="vuln-picker-name vuln-picker-empty">Empty</span>'
        emptyItem.onclick = () => { closeAddFindingDialog(); addFinding() }
        list.appendChild(emptyItem)

        vulns.forEach(vuln => {
            const item = document.createElement('div')
            item.className = 'vuln-picker-item'
            const sev = (vuln.severity || 'NONE').toLowerCase()
            const badgeClass = sev === 'none' ? 'badge-info' : `badge-${sev}`
            item.innerHTML = `
                <span class="vuln-picker-name">${escapeHtml(vuln.name)}</span>
                <span class="badge ${badgeClass}">${escapeHtml(vuln.severity || 'NONE')}</span>
            `
            item.onclick = () => { closeAddFindingDialog(); addFindingFromVuln(vuln) }
            list.appendChild(item)
        })
    } catch (e) {
        list.innerHTML = '<p class="vuln-picker-loading">Failed to load vulnerabilities.</p>'
    }
}

window.closeAddFindingDialog = () => {
    document.getElementById('addFindingDialog').classList.remove('open')
}

window.filterAddFindingDialog = () => {
    const query = document.getElementById('addFindingSearch').value.toLowerCase()
    const items = document.querySelectorAll('#addFindingDialogList .vuln-picker-item')
    
    items.forEach(item => {
        const name = item.querySelector('.vuln-picker-name').textContent.toLowerCase()
        if (name === 'empty' || name.includes(query)) {
            item.style.display = 'flex'
        } else {
            item.style.display = 'none'
        }
    })
}

window.addFindingFromVuln = (vuln) => {
    const cvssObj = parseCvssVector(vuln.cvss_vector)

    const finding = addFinding(true, {
        description: vuln.description || '',
        remediation: vuln.remediation || '',
    })

    const zid = finding.getAttribute('zid')
    const findingIndex = zidIndexes["pages.findings"].indexOf(zid)

    window.dataStore.pages.findings[findingIndex].name = vuln.name || ''
    window.dataStore.pages.findings[findingIndex].classification = vuln.classification || ''
    window.dataStore.pages.findings[findingIndex].remediationComplexity = vuln.remediation_complexity || 'Low'
    window.dataStore.pages.findings[findingIndex].remediationPriority = vuln.remediation_priority || 'Low'
    window.dataStore.pages.findings[findingIndex].vulnId = vuln.id || null

    const nameInput = finding.querySelector('[data-bind="name"]')
    if (nameInput) {
        nameInput.value = vuln.name || ''
        updateFindingName(vuln.name, zid)
    }

    const classInput = finding.querySelector('[data-bind="classification"]')
    if (classInput) classInput.value = vuln.classification || ''

    const remComplexSelect = finding.querySelector('[data-bind="remediationComplexity"]')
    if (remComplexSelect) remComplexSelect.value = vuln.remediation_complexity || 'Low'

    const remPriorSelect = finding.querySelector('[data-bind="remediationPriority"]')
    if (remPriorSelect) remPriorSelect.value = vuln.remediation_priority || 'Low'

    const cvssSection = finding.querySelector('.cvss-section')
    if (cvssSection) {
        Object.keys(cvssObj).forEach(metric => {
            const group = cvssSection.querySelector(`.metric-buttons[data-metric="${metric}"]`)
            if (group) {
                group.querySelectorAll('button').forEach(b => b.classList.remove('active'))
                const btn = group.querySelector(`button[data-value="${cvssObj[metric]}"]`)
                if (btn) btn.classList.add('active')
            }
        })
        updateCvssDisplay(cvssSection)
    }

    saveLocal()
}

async function doSaveFindingToVuln(zid, vulnId) {
    const findingIndex = zidIndexes["pages.findings"].indexOf(zid)
    const finding = window.dataStore.pages.findings[findingIndex]

    const descEditor = tinymce.get(`desc-${zid}`)
    const remedEditor = tinymce.get(`remed-${zid}`)

    const payload = {
        name: finding.name || '',
        description: descEditor ? DOMPurify.sanitize(descEditor.getContent()) : (finding.description || ''),
        classification: finding.classification || '',
        cvss_vector: finding.cvssString || 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N',
        cvss_score: finding.cvss || 0,
        severity: finding.severity || 'NONE',
        remediation_complexity: finding.remediationComplexity || 'Low',
        remediation_priority: finding.remediationPriority || 'Low',
        remediation: remedEditor ? DOMPurify.sanitize(remedEditor.getContent()) : (finding.remediation || ''),
    }

    const result = vulnId
        ? await apiUpdateVulnerability(vulnId, payload)
        : await apiCreateVulnerability(payload)

    if (!vulnId) {
        window.dataStore.pages.findings[findingIndex].vulnId = result.id
        saveLocal()
    }

    return result
}

function withButtonFeedback(btn, asyncFn) {
    const originalHTML = btn.innerHTML
    btn.disabled = true
    asyncFn()
        .then(() => {
            btn.style.color = '#16a34a'
            btn.style.borderColor = '#16a34a'
        })
        .catch(() => {
            btn.style.color = '#c41e3a'
            btn.style.borderColor = '#c41e3a'
        })
        .finally(() => {
            setTimeout(() => {
                btn.innerHTML = originalHTML
                btn.style.color = ''
                btn.style.borderColor = ''
                btn.disabled = false
            }, 1500)
        })
}

window.saveBackFinding = (zid) => {
    const findingIndex = zidIndexes["pages.findings"].indexOf(zid)
    const finding = window.dataStore.pages.findings[findingIndex]

    if (!finding.vulnId) {
        alert('This finding is not linked to a vulnerability in the database.\nUse "Save as new vulnerability" to create one.')
        return
    }

    const btn = document.querySelector(`.finding[zid="${zid}"] .finding-save-back`)
    withButtonFeedback(btn, () => doSaveFindingToVuln(zid, finding.vulnId))
}

window.saveFindingAsNewVuln = (zid) => {
    const btn = document.querySelector(`.finding[zid="${zid}"] .finding-save-new`)
    withButtonFeedback(btn, () => doSaveFindingToVuln(zid, null))
}

window.onSaveClick = downloadSaveFile
window.onOpenClick = importSaveFile
window.updateCvssDisplay = updateCvssDisplay
window.onRawEditButtonClicked = showRawEditPage

document.addEventListener('click', (e) => {
    const btn = e.target.closest('.metric-buttons button')
    if (!btn) return

    const group = btn.closest('.metric-buttons')
    group.querySelectorAll('button').forEach(b => b.classList.remove('active'))
    btn.classList.add('active')

    const section = btn.closest('.cvss-section')
    updateCvssDisplay(section)

    const findingZid = section.dataset.finding
    const findingIndex = zidIndexes["pages.findings"].indexOf(findingZid)
    if (findingIndex >= 0) {
        const metrics = window.dataStore.pages.findings[findingIndex]?.cvssObj
        if (metrics) emitFieldChange('cvss', `finding.${findingIndex}.cvssObj`, metrics)
    }
})

const reportMatch = window.location.pathname.match(/^\/reports\/(\d+)$/)
const reportId = reportMatch ? parseInt(reportMatch[1]) : null

window.onServerSaveClick = () => {
    if (!reportId) return
    const btn = document.getElementById('reportSaveBtn')
    const label = btn.querySelector('span')
    btn.disabled = true
    const originalText = label.textContent
    label.textContent = 'Saving...'
    saveToServer(reportId)
        .then(() => {
            label.textContent = 'Saved!'
            btn.style.color = '#16a34a'
            const navSaveBtn = document.getElementById('navSaveBtn')
            if (navSaveBtn) navSaveBtn.style.display = 'none'
        })
        .catch(() => {
            label.textContent = 'Error'
            btn.style.color = '#c41e3a'
        })
        .finally(() => {
            setTimeout(() => {
                label.textContent = originalText
                btn.style.color = ''
                btn.disabled = false
            }, 1500)
        })
}

window.addEventListener("load", async () => {
    const loader = document.getElementById('loadingOverlay')
    if (loader) loader.style.display = 'flex'

    await preloadTemplates()
    initBinds()

    // Attach collab focus/blur listeners to top-level global fields
    document.querySelectorAll('[data-bind^="global."]').forEach(el => {
        if (el.dataset.listInput || el.closest('[zid]')) return
        const fieldId = el.dataset.bind
        el.addEventListener('focus', () => emitFieldFocus(fieldId))
        el.addEventListener('blur',  () => emitFieldBlur(fieldId))
    })

    if (reportId) {
        const saveBtn = document.getElementById('reportSaveBtn')
        if (saveBtn) saveBtn.style.display = ''

        isLoading = true
        try {
            const report = await apiGetReport(reportId)
            if (report.content) loadFromServer(report.content)
        } catch (e) {
            console.error('Failed to load report', e)
        }

        setTimeout(() => {
            isLoading = false
            if (loader) loader.style.display = 'none'
        }, 500)

        // Start collaborative presence
        if (typeof _currentUserId !== 'undefined') {
            initCollab(reportId, _currentUserId)
        }
    } else {
        if (loader) loader.style.display = 'none'
    }
})
