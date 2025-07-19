document.addEventListener('DOMContentLoaded', () => {
    const toast = document.getElementById('toast');
    if (localStorage.getItem('formToast') === 'true') {
        toast.classList.add('show');
        setTimeout(() => {
            toast.classList.remove('show');
        }, 3000);
        localStorage.removeItem('formToast');
    }
});

document.querySelector('form').addEventListener('submit', () => {
    localStorage.setItem('formToast', 'true');
});
