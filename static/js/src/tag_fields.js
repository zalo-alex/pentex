import { saveLocal } from "./store.js";

function getArr(key) {
    if (!Array.isArray(window.dataStore.global[key])) window.dataStore.global[key] = [];
    return window.dataStore.global[key];
}

function renderTagField(el) {
    const key = el.dataset.tags;
    const list = el.querySelector(".tag-list");
    list.innerHTML = "";
    getArr(key).forEach((value, index) => {
        const chip = document.createElement("span");
        chip.className = "tag-chip";
        chip.textContent = value;

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "tag-chip-remove";
        remove.textContent = "×";
        remove.onclick = () => {
            window.updateData(() => {
                getArr(key).splice(index, 1);
                saveLocal();
            });
            renderTagField(el);
            syncPillGroups(key);
        };

        chip.appendChild(remove);
        list.appendChild(chip);
    });
}

function addTag(el, rawValue) {
    const value = rawValue.trim();
    if (!value) return;
    const key = el.dataset.tags;
    const arr = getArr(key);
    if (arr.includes(value)) return;
    window.updateData(() => {
        arr.push(value);
        saveLocal();
    });
    renderTagField(el);
    syncPillGroups(key);
}

function syncPillGroupEl(group) {
    const key = group.dataset.pills;
    const arr = getArr(key);
    group.querySelectorAll(".pill-btn").forEach((btn) => {
        btn.classList.toggle("active", arr.includes(btn.dataset.value));
    });
}

function syncPillGroups(key) {
    document.querySelectorAll(`.pill-group[data-pills="${key}"]`).forEach(syncPillGroupEl);
}

function syncTagFields(key) {
    document.querySelectorAll(`.tag-field[data-tags="${key}"]`).forEach(renderTagField);
}

export function initTagFields(base = document) {
    base.querySelectorAll(".tag-field[data-tags]").forEach((el) => {
        renderTagField(el);
        const input = el.querySelector(".tag-input-field");
        if (!input) return;

        input.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === ",") {
                e.preventDefault();
                addTag(el, input.value);
                input.value = "";
            } else if (e.key === "Backspace" && input.value === "") {
                const key = el.dataset.tags;
                const arr = getArr(key);
                if (arr.length) {
                    window.updateData(() => {
                        arr.pop();
                        saveLocal();
                    });
                    renderTagField(el);
                    syncPillGroups(key);
                }
            }
        });

        input.addEventListener("blur", () => {
            if (input.value.trim()) {
                addTag(el, input.value);
                input.value = "";
            }
        });
    });
}

export function initPillGroups(base = document) {
    base.querySelectorAll(".pill-group[data-pills]").forEach((group) => {
        syncPillGroupEl(group);
        group.querySelectorAll(".pill-btn").forEach((btn) => {
            btn.addEventListener("click", () => {
                const key = group.dataset.pills;
                const value = btn.dataset.value;
                const arr = getArr(key);
                const index = arr.indexOf(value);
                window.updateData(() => {
                    if (index === -1) arr.push(value);
                    else arr.splice(index, 1);
                    saveLocal();
                });
                syncPillGroupEl(group);
                syncTagFields(key);
            });
        });
    });
}

export function refreshTagFields(base = document) {
    base.querySelectorAll(".tag-field[data-tags]").forEach(renderTagField);
}

export function refreshPillGroups(base = document) {
    base.querySelectorAll(".pill-group[data-pills]").forEach(syncPillGroupEl);
}
