function openUploadAssetDialog() {
    document.getElementById('uploadAssetDialog')?.classList.add('open')
}
function closeUploadAssetDialog() {
    document.getElementById('uploadAssetDialog')?.classList.remove('open')
}
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeUploadAssetDialog()
})

function copyAssetUrl(url) {
    navigator.clipboard.writeText(url)
        .then(() => alert('Asset URL copied to clipboard.'))
}
