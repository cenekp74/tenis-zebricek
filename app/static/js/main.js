function setParentDisplayNone(element) {
    element.closest('.alert').style.display = 'none';
}

document.addEventListener('DOMContentLoaded', function () {
    const toggle = document.getElementById('navbarToggle');
    const menu = document.getElementById('navbarMenu');

    if (toggle && menu) {
        toggle.addEventListener('click', function () {
            const isOpen = menu.classList.toggle('is-open');
            toggle.setAttribute('aria-expanded', isOpen);
        });

        document.addEventListener('click', function (e) {
            if (!menu.contains(e.target) && !toggle.contains(e.target)) {
                menu.classList.remove('is-open');
                toggle.setAttribute('aria-expanded', 'false');
            }
        });
    }
});
