function toggleErrors(headerRow) {
    const icon = headerRow.querySelector('.collapse-icon');
    const expanded = headerRow.classList.toggle('expanded');
    icon.innerHTML = expanded ? '&#9660;' : '&#9654;';
    let row = headerRow.nextElementSibling;
    while (row && row.classList.contains('template-error-row')) {
        row.classList.toggle('collapsed', !expanded);
        row = row.nextElementSibling;
    }
}
