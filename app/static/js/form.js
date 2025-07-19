document.addEventListener('DOMContentLoaded', () => {
    const toast = document.getElementById('toast');
    if (toast && toast.textContent.trim() !== "") {
        toast.classList.add('show');
        setTimeout(() => {
            toast.classList.remove('show');
            toast.textContent = ""; // clear toast after hide
        }, 3000);
    }
});

document.querySelector('form').addEventListener('submit', () => {
    localStorage.setItem('formToast', 'true');
});