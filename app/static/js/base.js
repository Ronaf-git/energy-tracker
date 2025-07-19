(function() {
    const html = document.documentElement;
    if (localStorage.getItem('darkMode') === 'enabled') {
        html.classList.add('dark-mode');
    }
    // Add class to show page only after applying dark mode
    html.classList.add('js-ready');
})();

document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.getElementById('darkModeToggle');
    const html = document.documentElement;

    if (!toggle) return;  // Safety check

    // Initialize button text based on current mode
    if (html.classList.contains('dark-mode')) {
        toggle.textContent = '☀️';
    } else {
        toggle.textContent = '🌙';
    }

    toggle.addEventListener('click', () => {
        html.classList.toggle('dark-mode');
        if (html.classList.contains('dark-mode')) {
            toggle.textContent = '☀️';
            localStorage.setItem('darkMode', 'enabled');
        } else {
            toggle.textContent = '🌙';
            localStorage.setItem('darkMode', 'disabled');
        }
    });
});
