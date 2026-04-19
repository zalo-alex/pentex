import { zidIndexes, initBinds, getFromPath } from "./store.js";

export const listInputs = {
    "abbreviations": {
        "default": { abbreviation: "", definition: "" },
        "storeKey": "global.abbreviations",
        "z": "abbreviation",
        "bind": "global.abbreviations"
    },
    "auditors": {
        "default": { fullName: "", email: "" },
        "storeKey": "global.auditors",
        "z": "auditor",
        "bind": "global.auditors"
    },
    "scopes": {
        "default": { name: "" },
        "storeKey": "global.scopes",
        "z": "scope",
        "bind": "global.scopes"
    },
    "testAccess": {
        "default": { identifier: "", role: "", resource: "" },
        "storeKey": "global.testAccess",
        "z": "testAccess",
        "bind": "global.testAccess"
    },
    "diffusionTable": {
        "default": { company: "", name: "", role: "", email: "" },
        "storeKey": "global.diffusionTable",
        "z": "diffusionRow",
        "bind": "global.diffusionTable"
    },
    "versionHistory": {
        "default": { version: "", date: "", author: "", changes: "", description: "" },
        "storeKey": "global.versionHistory",
        "z": "versionHistoryRow",
        "bind": "global.versionHistory"
    }
}

function getListStore(listProperties) {
    return getFromPath(window.dataStore, listProperties.storeKey);
}

window.addListItem = (inputId, addDefaults = true) => {
    const listProperties = listInputs[inputId]
    let clone = z.create(listProperties.z)
    let zid = clone.getAttribute("zid")
    if (zidIndexes[listProperties.bind] == undefined) zidIndexes[listProperties.bind] = []
    zidIndexes[listProperties.bind].push(zid)
    if (addDefaults) getListStore(listProperties).push({...listProperties.default})
    initBinds(clone)
    return clone
}

window.removeListItem = (inputId, zid) => {
    const listProperties = listInputs[inputId]
    updateData(() => {
        let index = zidIndexes[listProperties.bind].indexOf(zid);
        zidIndexes[listProperties.bind].splice(index, 1);
        getListStore(listProperties).splice(index, 1);
        z.delete(zid)
    })
}