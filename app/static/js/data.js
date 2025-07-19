document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById('filterForm');

  form.querySelectorAll('input, select').forEach(element => {
    element.addEventListener('change', () => {
      form.submit();
    });
  });
});
