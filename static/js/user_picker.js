(function () {
    function initUserPicker(root) {
        const select = root.querySelector('.user-picker__native');
        const searchInput = root.querySelector('.user-picker__search');
        const options = Array.from(root.querySelectorAll('.user-picker__option'));
        const emptyMessage = root.querySelector('[data-user-picker-empty]');

        if (!select || !searchInput || !options.length) {
            return;
        }

        function setSelected(option) {
            options.forEach((item) => {
                item.classList.remove('is-selected');
                item.setAttribute('aria-selected', 'false');
            });
            option.classList.add('is-selected');
            option.setAttribute('aria-selected', 'true');
            select.value = option.dataset.value;
            select.dispatchEvent(new Event('change', { bubbles: true }));
        }

        function filterOptions(query) {
            const normalized = query.trim().toLowerCase();
            let visibleCount = 0;

            options.forEach((option) => {
                const haystack = option.dataset.search || '';
                const matches = !normalized || haystack.includes(normalized);
                option.classList.toggle('is-hidden', !matches);
                if (matches) {
                    visibleCount += 1;
                }
            });

            if (emptyMessage) {
                emptyMessage.classList.toggle('d-none', visibleCount > 0);
            }
        }

        options.forEach((option) => {
            option.addEventListener('click', () => setSelected(option));
        });

        searchInput.addEventListener('input', () => filterOptions(searchInput.value));

        const selected = options.find((option) => option.classList.contains('is-selected'));
        if (selected) {
            selected.scrollIntoView({ block: 'nearest' });
        }
    }

    function initAll(scope) {
        (scope || document).querySelectorAll('[data-user-picker]').forEach(initUserPicker);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => initAll());
    } else {
        initAll();
    }
})();
