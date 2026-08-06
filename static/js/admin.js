// ── Tab logic ──
const TABS = ['users', 'categories', 'templates', 'logs'];

function activateTab(name) {
    if (!TABS.includes(name)) name = 'users'
    TABS.forEach(t => {
        document.querySelector(`.admin-tab[data-tab="${t}"]`).classList.toggle('active', t === name)
        document.getElementById(`tab-${t}`).classList.toggle('active', t === name)
    })
    history.replaceState(null, '', '#' + name)
}

// On load: pick tab from hash, or auto-detect logs tab if filter params present
const hash = location.hash.replace('#', '')
const params = new URLSearchParams(location.search)
const hasLogParams = params.has('log_action') || params.has('log_user') || params.has('log_page')
activateTab(hash || (hasLogParams ? 'logs' : 'users'))

document.querySelectorAll('.admin-tab').forEach(tab => {
    tab.addEventListener('click', () => activateTab(tab.dataset.tab))
})

// ── Dialogs ──
function openNewUserDialog() {
    document.getElementById('newUserDialog').classList.add('open')
    setTimeout(() => document.getElementById('newUsername').focus(), 50)
}
function closeNewUserDialog() {
    document.getElementById('newUserDialog').classList.remove('open')
}
document.getElementById('newUsername').addEventListener('keydown', e => {
    if (e.key === 'Escape') closeNewUserDialog()
})

function copyInvite(url) {
    navigator.clipboard.writeText(url).then(() => alert('Invite link copied to clipboard.'))
}

function openChangePasswordDialog(userId, username) {
    document.getElementById('changePasswordTitle').textContent = 'Set password for ' + username
    document.getElementById('changePasswordForm').action = '/admin/users/' + userId + '/change-password'
    document.getElementById('changePasswordInput').value = ''
    document.getElementById('changePasswordConfirm').value = ''
    document.getElementById('changePasswordDialog').classList.add('open')
    setTimeout(() => document.getElementById('changePasswordInput').focus(), 50)
}
function closeChangePasswordDialog() {
    document.getElementById('changePasswordDialog').classList.remove('open')
}
document.getElementById('changePasswordInput').addEventListener('keydown', e => {
    if (e.key === 'Escape') closeChangePasswordDialog()
})

function openEditProfileDialog(btn) {
    const { userId, username, fullName, email } = btn.dataset
    document.getElementById('editProfileTitle').textContent = 'Edit profile — ' + username
    document.getElementById('editProfileForm').action = '/admin/users/' + userId + '/profile'
    document.getElementById('editProfileFullName').value = fullName || ''
    document.getElementById('editProfileEmail').value = email || ''
    document.getElementById('editProfileDialog').classList.add('open')
    setTimeout(() => document.getElementById('editProfileFullName').focus(), 50)
}
function closeEditProfileDialog() {
    document.getElementById('editProfileDialog').classList.remove('open')
}
document.getElementById('editProfileFullName').addEventListener('keydown', e => {
    if (e.key === 'Escape') closeEditProfileDialog()
})

function openNewCategoryDialog() {
    document.getElementById('newCategoryDialog').classList.add('open')
    setTimeout(() => document.getElementById('newCategoryName').focus(), 50)
}
function closeNewCategoryDialog() {
    document.getElementById('newCategoryDialog').classList.remove('open')
}
document.getElementById('newCategoryName').addEventListener('keydown', e => {
    if (e.key === 'Escape') closeNewCategoryDialog()
})

function openNewTemplateDialog() {
    document.getElementById('newTemplateDialog').classList.add('open')
    setTimeout(() => document.getElementById('newTemplateName').focus(), 50)
}
function closeNewTemplateDialog() {
    document.getElementById('newTemplateDialog').classList.remove('open')
}
document.getElementById('newTemplateName').addEventListener('keydown', e => {
    if (e.key === 'Escape') closeNewTemplateDialog()
})
