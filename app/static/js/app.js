const savedTheme = localStorage.getItem('theme') || 'light';
document.documentElement.setAttribute('data-bs-theme', savedTheme);
updateIcon(savedTheme);
function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-bs-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-bs-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateIcon(newTheme);
}
function updateIcon(theme) {
    const icon = document.getElementById('themeIcon');
    if (icon) { icon.className = theme === 'dark' ? 'bi bi-sun-fill fs-5' : 'bi bi-moon-stars-fill fs-5'; }
}

// Global Alert Modernization
document.addEventListener('DOMContentLoaded', () => {
    // Function to configure and show SweetAlert
    const showSweetAlert = (msg, callback) => {
        const isDark = document.documentElement.getAttribute('data-bs-theme') === 'dark';
        Swal.fire({
            title: '¿Estás seguro?',
            text: msg,
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#4f46e5',
            cancelButtonColor: '#dc3545',
            confirmButtonText: '<i class="bi bi-check-lg pe-1"></i> Sí, confirmar',
            cancelButtonText: 'Cancelar',
            background: isDark ? '#1e293b' : '#ffffff',
            color: isDark ? '#f8fafc' : '#0f172a',
            customClass: {
                popup: 'rounded-4 shadow-lg border border-secondary border-opacity-10'
            }
        }).then((result) => {
            if (result.isConfirmed) {
                callback();
            }
        });
    };

    // Intercept form submissions
    document.querySelectorAll('form[onsubmit*="return confirm"]').forEach(form => {
        const onsubmitValue = form.getAttribute('onsubmit');
        const match = onsubmitValue.match(/confirm\(['"](.*?)['"]\)/);
        if (match && match[1]) {
            const msg = match[1];
            form.removeAttribute('onsubmit');
            form.addEventListener('submit', function(e) {
                e.preventDefault();
                showSweetAlert(msg, () => { form.submit(); });
            });
        }
    });

    // Intercept onclick attributes
    document.querySelectorAll('[onclick*="return confirm"]').forEach(el => {
        const onclickValue = el.getAttribute('onclick');
        const match = onclickValue.match(/confirm\(['"](.*?)['"]\)/);
        if (match && match[1]) {
            const msg = match[1];
            el.removeAttribute('onclick');
            el.addEventListener('click', function(e) {
                e.preventDefault();
                showSweetAlert(msg, () => {
                    const href = el.getAttribute('href');
                    const form = el.closest('form');
                    if (href && href !== '#' && href !== '') {
                        window.location.href = href;
                    } else if (form) {
                        form.submit();
                    } else {
                        // Default behavior if it was just a button doing nothing
                        el.click(); // This might recurse if not handled carefully, but we removed onclick so it's safe.
                    }
                });
            });
        }
    });
});
