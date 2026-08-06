import { zidIndexes, getFromPath } from "./store.js";
import { apiGetAuditorUsers } from "./api.js";

let auditorUsersById = new Map();

export async function loadAuditorUsers() {
    try {
        const users = await apiGetAuditorUsers();
        auditorUsersById = new Map(users.map(u => [u.id, u]));
        populateAuditorSelects(users);
    } catch (e) {
        console.error('Failed to load auditor users', e);
    }
}

function populateAuditorSelects(users) {
    document.querySelectorAll('select[data-bind="userId"]').forEach((select) => {
        const otherOption = select.querySelector('option[value="__other__"]');
        users.forEach((u) => {
            const opt = document.createElement('option');
            opt.value = String(u.id);
            opt.textContent = u.full_name || u.username;
            select.insertBefore(opt, otherOption);
        });
    });
}

function syncAuditorRowUI(row, itemData) {
    const select = row.querySelector('select[data-bind="userId"]');
    if (!select) return;
    const known = itemData.userId && auditorUsersById.has(itemData.userId);
    select.value = known ? String(itemData.userId) : '__other__';
    row.classList.toggle('auditor-other', !known);
}

window.onAuditorSelectChange = (select) => {
    const row = select.closest('[zid]');
    const idx = zidIndexes['global.auditors'].indexOf(row.getAttribute('zid'));
    if (idx === -1) return;
    window.updateData(() => {
        const entry = getFromPath(window.dataStore, 'global.auditors')[idx];
        if (select.value === '__other__' || select.value === '') {
            entry.userId = select.value === '__other__' ? '__other__' : '';
            row.classList.toggle('auditor-other', select.value === '__other__');
        } else {
            const user = auditorUsersById.get(select.value);
            entry.userId = user.id;
            entry.fullName = user.full_name || '';
            entry.email = user.email || '';
            row.querySelector('[data-bind="fullName"]').value = entry.fullName;
            row.querySelector('[data-bind="email"]').value = entry.email;
            row.classList.remove('auditor-other');
        }
    });
};

window.onAuditorManualInputChange = (input) => {
    const row = input.closest('[zid]');
    if (!row) return;
    const idx = zidIndexes['global.auditors'].indexOf(row.getAttribute('zid'));
    if (idx === -1) return;
    window.updateData(() => {
        const entry = getFromPath(window.dataStore, 'global.auditors')[idx];
        entry[input.dataset.bind] = input.value;
    });
};

window.onListItemImported = (listInputId, row, itemData) => {
    if (listInputId === 'auditors') syncAuditorRowUI(row, itemData);
};
