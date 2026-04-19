async function loadOwners() {
    const [ownersRes, usersRes] = await Promise.all([
        fetch('/api/reports/' + _reportId + '/owners'),
        fetch('/api/users')
    ]);
    if (!ownersRes.ok || !usersRes.ok) return;
    const owners = await ownersRes.json();
    const users  = await usersRes.json();

    const list = document.getElementById('ownersList');
    list.innerHTML = '';
    owners.forEach(o => {
        const item = document.createElement('div');
        item.className = 'list-input-item';
        item.dataset.ownerId = o.id;
        item.innerHTML =
            '<span style="flex:1;font-size:13px;padding:4px 2px;">' + escapeHtml(o.username) + '</span>' +
            '<button class="remove-abbr" onclick="removeOwner(' + o.id + ')" ' +
            (owners.length <= 1 ? 'disabled title="Cannot remove the last owner"' : '') +
            '>×</button>';
        list.appendChild(item);
    });

    const sel = document.getElementById('ownerSelectInput');
    const ownerIds = new Set(owners.map(o => o.id));
    sel.innerHTML = '<option value="">Select a user to add…</option>';
    users.filter(u => !ownerIds.has(u.id)).forEach(u => {
        const opt = document.createElement('option');
        opt.value = u.id;
        opt.textContent = u.username;
        sel.appendChild(opt);
    });
}

async function addOwner() {
    const sel = document.getElementById('ownerSelectInput');
    const userId = parseInt(sel.value);
    if (!userId) return;
    const username = sel.options[sel.selectedIndex].text;
    const res = await fetch('/api/reports/' + _reportId + '/owners', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
        body: JSON.stringify({ username })
    });
    if (res.ok) loadOwners();
}

async function removeOwner(userId) {
    const res = await fetch('/api/reports/' + _reportId + '/owners/' + userId, { method: 'DELETE', headers: { 'X-CSRFToken': csrfToken() } });
    if (res.ok) loadOwners();
}

function escapeHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

document.addEventListener('DOMContentLoaded', loadOwners);
