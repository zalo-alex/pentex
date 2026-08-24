import { getModifiedTemplates, importTemplates } from "./templates.js";
import { apiSaveReport } from "./api.js";

window.dataStore = {
    global: {
        "clientName": "Example",
        "testType": "Web",
        "approaches": [],
        "blackbox": false,
        "graybox": false,
        "whitebox": false,
        "reference": "",
        "revision": "1.0",
        "abbreviations": [],
        "auditors": [],
        "scopes": [],
        "testAccess": [],
        "diffusionTable": [],
        "versionHistory": [],
        "discoveryEntryPoints": [],
        "discoveryTechnologies": [],
        "discoveryServerPlatform": "",
        "discoveryClientTech": [],
        "discoveryAuthMechanisms": [],
        "discoverySessionManagement": [],
        "discoveryMappedFeatures": [],
        "discoveryIntegrations": [],
        "discoveryApiEndpoints": [],
        "discoveryStaticDynamicContent": "",
        "discoveryAccessControlBehavior": "",
        "discoveryParameters": [],
        "discoverySubdomains": [],
        "discoverySecurityHeaders": [],
        "discoveryIpRanges": [],
        "discoveryDnsEntries": [],
        "discoveryOpenPorts": [],
        "discoveryServiceBanners": [],
        "discoveryHostingProvider": "",
        "discoveryWafLb": [],
        "discoveryTlsCertDetails": "",
        "discoveryHttpFingerprint": [],
        "discoveryInternalServices": [],
        "discoveryRemoteAccess": [],
        "discoveryStagingEnvs": [],
        "discoveryDebugServices": [],
        "wstgResults": {},
        "wstgProof": {}
    },
    pages: {
        "findings": []
    }
}

// Populated from the loaded report's saved pagesCount (see importData below) — the
// bundle of page names/counts is now determined server-side by the report's linked
// Template, not a fixed constant here.
export let pagesCount = {}

// Some parts doesn't check if the key exists, so manually init it here
export const zidIndexes = {
    "pages.findings": []
}

function collectData() {
    return {
        dataStore: window.dataStore,
        pagesCount,
        templates: getModifiedTemplates()
    }
}

export function getFromPath(object, path) {
    const keys = path.split('.');
    let current = object;
    for (const key of keys) {
        if (current == null) return undefined;
        current = current[key];
    }
    return current;
}

function setFromPath(object, path, value) {
    const keys = path.split('.');
    let current = object;
    for (let i = 0; i < keys.length - 1; i++) {
        const key = keys[i];
        if (current[key] == null) current[key] = {};
        current = current[key];
    }
    current[keys[keys.length - 1]] = value;
}

export function saveLocal() {
    localStorage.setItem('pentex-data', JSON.stringify(collectData()));
}

export function getLocal() {
    return JSON.parse(localStorage.getItem('pentex-data'));
}

export function initBind(input) {
    let bindKey = input.dataset.bind
    let parentBindElement = input.closest("[zid][data-bind]")
    let parentBind = parentBindElement ? parentBindElement.dataset.bind : undefined
    let parentBindZid = parentBindElement ? parentBindElement.getAttribute("zid") : undefined

    input.addEventListener("input", () => {
        updateData(() => {
            let value = null;
            if (input.type == "checkbox") {
                value = input.checked
            } else {
                value = input.value
            }
            let object = window.dataStore
            if (parentBind) {
                object = getFromPath(object, parentBind)[zidIndexes[parentBind].indexOf(parentBindZid)]
            }
            setFromPath(object, bindKey, value)
            saveLocal()

            input.dispatchEvent(new CustomEvent('collab:field-change', {
                bubbles: true,
                detail: { bindKey, value, parentBind, parentBindZid }
            }))

        })
    })
}

export function initBinds(base = document) {
    const bindInputs = base.querySelectorAll("[data-bind]")
    bindInputs.forEach(initBind)
}

export function importSaveFile() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.style.display = 'none';
    document.body.appendChild(input);
    input.addEventListener('change', () => {
        const file = input.files[0];
        if (!file) { input.remove(); return; }
        const reader = new FileReader();
        reader.onload = () => {
            const data = JSON.parse(reader.result);
            importData(data);
            input.remove();
        };
        reader.readAsText(file);
    });
    input.click();
}

export function importData(data) {
    pagesCount = data.pagesCount
    importDataStore(data.dataStore)
    importTemplates(data.templates)
}

export function importDataStore(newDataStore) {
    window.dataStore = newDataStore
    saveLocal();

    Object.keys(window.dataStore.global).forEach((key) => {
        const bindElement = document.querySelector(`[data-bind='global.${key}'`)
        if (!bindElement) return
        
        if (bindElement.type == "text" || bindElement.nodeName == "SELECT") {
            bindElement.value = window.dataStore.global[key]

        } else if (bindElement.type == "checkbox") {
            bindElement.checked = window.dataStore.global[key]

        } else if (bindElement.dataset.listInput) {
            const listInputId = bindElement.dataset.listInput
            for (let i = 0; i < window.dataStore.global[key].length; i++) {
                const itemData = window.dataStore.global[key][i]
                let listItem = addListItem(listInputId, false)
                Object.keys(itemData).forEach((subkey) => {
                    const el = listItem.querySelector(`[data-bind='${subkey}']`)
                    if (el) el.value = itemData[subkey]
                })
                if (window.onListItemImported) window.onListItemImported(listInputId, listItem, itemData)
            }

        } else {
            console.log("Unknown element", bindElement)
        }
    })

    window.dataStore.pages.findings.forEach((findingData) => {
        let finding = addFinding(false, {
            name: findingData.name || '',
            description: findingData.description || '',
            remediation: findingData.remediation || '',
            poc: findingData.poc || ''
        })
        Object.keys(findingData).forEach((key) => {
            if (key == "cvssObj") {
                const cvssSection = finding.querySelector('.cvss-section')
                if (cvssSection && findingData.cvssObj) {
                    Object.keys(findingData.cvssObj).forEach((metric) => {
                        const group = cvssSection.querySelector(`.metric-buttons[data-metric="${metric}"]`)
                        if (group) {
                            group.querySelectorAll('button').forEach(b => b.classList.remove('active'))
                            const btn = group.querySelector(`button[data-value="${findingData.cvssObj[metric]}"]`)
                            if (btn) btn.classList.add('active')
                        }
                    })
                    updateCvssDisplay(cvssSection)
                }
            } else if (key === "description" || key === "remediation" || key === "poc") {
                // Handled via TinyMCE initialContent
            } else {
                const bindElement = finding.querySelector(`[data-bind='${key}'`)
                if (!bindElement) return

                bindElement.value = findingData[key]
            }
        })
    })
}

export function downloadSaveFile() {
    const dataJson = JSON.stringify(collectData(), null, 2);
    const blob = new Blob([dataJson], { type: 'application/json' });
    const url = URL.createObjectURL(blob);

    const link = document.createElement('a');
    link.href = url;
    link.download = 'pentex-save.json';
    link.click();

    URL.revokeObjectURL(url);
}

export async function saveToServer(reportId) {
    const dataJson = JSON.stringify(collectData());
    return await apiSaveReport(reportId, dataJson)
}

export function loadFromServer(contentJson) {
    if (!contentJson) return
    const data = JSON.parse(contentJson)
    importData(data)
} 