const fields = [{ name: 'record_date', label: 'Date', type: 'date' }].concat(window.editFields || []);
const deletedDates = [];


const tbody = document.querySelector('#editableTable tbody');
const form = document.getElementById('editForm');
const input = document.getElementById('tableDataInput');
const addRowBtn = document.getElementById('addRowBtn');


function applyDataTypes() {
    tbody.querySelectorAll('tr').forEach(tr => {
        tr.querySelectorAll('td').forEach((td, i) => {
            td.dataset.type = fields[i]?.type || 'text'; // fallback à 'text' si pas défini
        });
    });
}

applyDataTypes();


function placeCaretAtEnd(el) {
    el.focus();
    if (typeof window.getSelection != "undefined"
        && typeof document.createRange != "undefined") {
        var range = document.createRange();
        range.selectNodeContents(el);
        range.collapse(false);
        var sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
    }
}


tbody.addEventListener('input', e => {
    const target = e.target;
    if (target.tagName === 'TD' && target.isContentEditable) {
        const type = target.dataset.type;
        const val = target.innerText.trim();

        if (type === 'number') {
            if (!/^[-\d.,]*$/.test(val)) {
                target.innerText = val.slice(0, -1);
                placeCaretAtEnd(target);
            }
        }
    }
});

// add row
addRowBtn.addEventListener('click', () => {
    const newRow = document.createElement('tr');

    fields.forEach((field, i) => {
        const newCell = document.createElement('td');
        newCell.contentEditable = "true";
        newCell.dataset.type = field.type;
        newCell.innerText = '';  // Start empty
        newRow.appendChild(newCell);
    });

    const deleteCell = document.createElement('td');
    const deleteBtn = document.createElement('button');
    deleteBtn.type = "button";
    deleteBtn.textContent = "🗑";
    deleteBtn.classList.add("delete-row-btn");
    deleteCell.appendChild(deleteBtn);
    newRow.appendChild(deleteCell);

    tbody.appendChild(newRow);
    applyDataTypes();
    newRow.cells[0]?.focus();  // Focus first cell
});


//delete row
tbody.addEventListener('click', e => {
    if (e.target.classList.contains('delete-row-btn')) {
        const row = e.target.closest('tr');
        if (row) {
            const recordDateCell = row.querySelector('td');
            const recordDate = recordDateCell?.innerText.trim();
            if (recordDate) {
                deletedDates.push(recordDate);
            }
            row.remove();
        }
    }
});


// Validation
form.addEventListener('submit', function(e) {
    console.log('Submit détecté');
    const rowsData = [];
    const datesSeen = new Set();
    let valid = true;

    tbody.querySelectorAll('tr').forEach(tr => {
        const rowObj = {};
        const cells = tr.querySelectorAll('td');

        for (let i = 0; i < fields.length; i++) {
            const td = cells[i];
            const val = td.innerText.trim();
            const type = td.dataset.type;
            const label = fields[i]?.label || `Colonne ${i + 1}`;
            const name = fields[i]?.name;

            if (type === 'number' && val !== '') {
                const numVal = parseFloat(val.replace(',', '.'));
                if (isNaN(numVal)) {
                    alert(`Erreur : La valeur "${val}" dans la colonne "${label}" doit être un nombre.`);
                    td.focus();
                    valid = false;
                    e.preventDefault();
                    return;
                }
                rowObj[name] = numVal;
            } else if (type === 'date') {
                const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
                if (!dateRegex.test(val)) {
                    alert(`Erreur : La valeur "${val}" dans la colonne "${label}" doit être une date valide au format YYYY-MM-DD.`);
                    td.focus();
                    valid = false;
                    e.preventDefault();
                    return;
                }
                if (datesSeen.has(val)) {
                    alert(`Erreur : La date "${val}" est en double. Chaque ligne doit avoir une date unique.`);
                    td.focus();
                    valid = false;
                    e.preventDefault();
                    return;
                }
                datesSeen.add(val);
                rowObj[name] = val;
            } else {
                rowObj[name] = val;
            }
        }

        if (valid) {
            rowsData.push(rowObj);
        }
    });

    if (!valid) return;
    // Append deleted rows
    deletedDates.forEach(date => {
        rowsData.push({
            record_date: date,
            _delete: true
        });
    });

    input.value = JSON.stringify(rowsData);
    console.log("Données JSON à envoyer :", input.value);
});


// Show toast if flag is in localStorage
window.addEventListener('DOMContentLoaded', () => {
    const toast = document.getElementById('toast');
    if (localStorage.getItem('showToast') === 'true') {
        toast.classList.add('show');
        setTimeout(() => {
            toast.classList.remove('show');
        }, 3000);
        localStorage.removeItem('showToast');
    }
});

// Before submitting the form, set toast flag
document.getElementById('editForm').addEventListener('submit', () => {
    localStorage.setItem('showToast', 'true');
});
