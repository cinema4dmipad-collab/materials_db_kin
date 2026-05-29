    function bindDuplicateButton(row) {
        const dupBtn = row.querySelector('.duplicate-row-btn');
        if (!dupBtn) return;
        dupBtn.addEventListener('click', () => {
            // collect current values
            const values = {};
            row.querySelectorAll('[name]').forEach(inp => {
                // replace current index with placeholder __idx__
                const placeholderName = inp.name.replace(/-\d+-/, '-__idx__-');
                values[placeholderName] = inp.value;
            });
            const nextIdx = getNextIndex();
            const template = document.getElementById('field-row-template');
            let html = template.innerHTML.replace(/__idx__/g, nextIdx);
            // insert collected values
            Object.entries(values).forEach(([namePattern, val]) => {
                const regex = new RegExp(namePattern.replace('__idx__', nextIdx), 'g');
                html = html.replace(regex, val);
            });
            const tbody = document.getElementById('structure-field-rows');
            tbody.insertAdjacentHTML('beforeend', html);
            const newRow = tbody.lastElementChild;
            if (newRow) {
                bindFieldNameAutofill(newRow);
                bindDeleteButtons(newRow);
                bindDuplicateButton(newRow);
            }
            const totalInput = document.querySelector('[name$="-TOTAL_FORMS"]');
            if (totalInput) totalInput.value = nextIdx + 1;
        });
    }