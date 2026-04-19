function csrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.content ?? ''
}

window.addEventListener("load", () => {
    document.querySelectorAll(".flash").forEach((flash, i) => setTimeout(() => {
        flash.remove()
    }, 5000 + i*1000))
})