import Handlebars from "./handlebars.js";
import { pagesCount } from "./store.js"

Handlebars.registerHelper('or', (...args) => args.slice(0, -1).some(Boolean));

export const templateCache = {};
export const rawTemplateCache = {};
let modifiedKeys = [];

export const fetchPageTemplate = async (name) => {
    if (templateCache[name]) {
        return templateCache[name];
    }

    let res = await fetch(`/api/templates/${_activeTemplateId}/pages/${name}.hbs/raw`)
    let text = await res.text()
    rawTemplateCache[name] = text;
    templateCache[name] = Handlebars.compile(text);
    return templateCache[name]
}

export const preloadTemplates = async () => {
    let res = await fetch(`/api/templates/${_activeTemplateId}/pages`)
    let pages = await res.json()
    for (let page of pages) {
        if (!page.filename.endsWith(".hbs")) continue
        let name = page.filename.slice(0, -4)
        rawTemplateCache[name] = page.content
        templateCache[name] = Handlebars.compile(page.content)
    }
    if (!templateCache["headers"]) await fetchPageTemplate("headers")
}

export const getTemplate = (name, index) => {
    let cacheKey = `${name}-${index}`
    if (!templateCache[cacheKey]) {
        templateCache[cacheKey] = templateCache[name]
    }

    return templateCache[cacheKey]
}

export const getRawTemplate = (name, index) => {
    let cacheKey = `${name}-${index}`
    if (!(cacheKey in rawTemplateCache)) {
        rawTemplateCache[cacheKey] = rawTemplateCache[name]
    }

    return rawTemplateCache[cacheKey]
}

export const updateTemplate = (key, value) => {
    if (!modifiedKeys.includes(key)) modifiedKeys.push(key)
    rawTemplateCache[key] = value
    templateCache[key] = Handlebars.compile(value)
}

export const getModifiedTemplates = () => {
    let modifiedTemplates = {}
    for (let key of modifiedKeys) {
        modifiedTemplates[key] = rawTemplateCache[key]
    }
    return modifiedTemplates
}

export const importTemplates = (templates) => {
    Object.keys(templates).forEach(key => {
        updateTemplate(key, templates[key])
    })
}