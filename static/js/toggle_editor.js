window.toggleEditor = function(header) {
    const section = header.parentElement
    const content = section.querySelector('.editor-content')
    const toggle  = header.querySelector('.editor-toggle')
    const collapsed = section.classList.toggle('collapsed')
    content.style.display = collapsed ? 'none' : 'block'
    toggle.textContent   = collapsed ? '▶' : '▼'
}
