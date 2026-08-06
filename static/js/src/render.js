import { getTemplate, rawTemplateCache } from "./templates.js";

import { pagesCount } from "./store.js";

let figureIndex = 0
let figures = []
zp.pre("pages img:not([no-figure])", ({element, outer}) => {
    let figureName = `Figure ${++figureIndex} - ${element.getAttribute("alt")}`
    figures.push({name: figureName, index: figureIndex})
    return `${outer}<span class="img-alt" id="figure-${figureIndex}" style="scroll-margin-top: ${parseInt(element.getAttribute('height'))+100}px">${figureName}</span>`
}, true, false)

export const renderHTML = () => {
    let finalRender = ""

    for (let pageName of Object.keys(pagesCount)) {
        for (let i = 0; i < pagesCount[pageName]; i++) {
            let currentPageData;
            if (dataStore.pages[pageName] != undefined) {
                currentPageData = dataStore.pages[pageName][i]
            }

            let template = getTemplate(pageName, i)
            // TODO: refactor computed template data (indexedFindings, etc.) into a dedicated function
            const indexedFindings = (dataStore.pages.findings || []).map((f, idx) => ({ ...f, index: idx + 1 }))
            let finalData = { ...dataStore.global, ...dataStore.pages, findings: indexedFindings, figures, ...currentPageData, index: i+1, lastVersion: () => dataStore.global.versionHistory.at(-1)?.version }
            const renderedPage = template(finalData)
            
            // This could break templates, it should be parsing HTML right, but it adds <html><head><body>
            const parser = new DOMParser();
            const doc = parser.parseFromString(renderedPage, "text/html");
            const page = doc.querySelector("page");
            page.setAttribute("template-id", `${pageName}-${i}`);
            const serializer = new XMLSerializer();
            const updatedRenderedPage = serializer.serializeToString(doc);

            finalRender += updatedRenderedPage;
        }
    }
    
    return finalRender
}

export const importHeaders = () => {
    document.querySelector(".headers-container").innerHTML = rawTemplateCache["headers"]
}

export const renderPages = () => {
    const previousScrollY = window.scrollY
    importHeaders()
    let pagesContainer = document.querySelector("pages")
    pagesContainer.innerHTML = renderHTML()
    z = { ...z, ...dataStore.global }
    figureIndex = 0
    figures = []
    z.batchRender(() => {
        zpages.updatePages()
        Prism.highlightAllUnder(pagesContainer)
        addRawEditButtons()
        window.scrollTo(0, previousScrollY)
    })
}

export function addRawEditButtons() {
    const pages = document.querySelectorAll("page")
    pages.forEach((page) => {
        z.createIn("rawEditButton", page, page.getAttribute("pageId"))
    })
}