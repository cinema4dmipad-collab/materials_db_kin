(function () {
    'use strict';

    function getCheckboxes(widget) {
        var container = widget.querySelector('.group-picker-checkboxes');
        if (!container) {
            return [];
        }
        return Array.from(container.querySelectorAll('input[type="checkbox"]'));
    }

    function findCheckbox(widget, groupId) {
        return getCheckboxes(widget).find(function (checkbox) {
            return checkbox.value === groupId;
        }) || null;
    }

    function selectedIds(widget) {
        return getCheckboxes(widget)
            .filter(function (checkbox) { return checkbox.checked; })
            .map(function (checkbox) { return checkbox.value; });
    }

    function initWidget(widget) {
        if (widget.dataset.groupPickerBound === 'true') {
            return;
        }
        widget.dataset.groupPickerBound = 'true';

        var typingInput = widget.querySelector('.group-picker-typing');
        var chipsContainer = widget.querySelector('.tag-input-chips');
        var composer = widget.querySelector('.tag-input-composer');
        var existingBlock = widget.querySelector('.tag-input-existing');
        var existingLabel = widget.querySelector('.tag-input-existing__label');
        var existingHint = widget.querySelector('.tag-input-existing__hint');
        var emptyMessage = widget.querySelector('.tag-input-existing__empty');
        if (!typingInput || !chipsContainer || !composer) {
            return;
        }

        function renderChips() {
            chipsContainer.innerHTML = '';
            getCheckboxes(widget).forEach(function (checkbox) {
                if (!checkbox.checked) {
                    return;
                }
                var groupName = checkbox.dataset.groupName || checkbox.value;
                var chip = document.createElement('span');
                chip.className = 'tag-input-chip entity-tag tone-tag';
                chip.dataset.groupId = checkbox.value;

                var label = document.createElement('span');
                label.className = 'entity-tag__text';
                label.textContent = groupName;

                var removeButton = document.createElement('button');
                removeButton.type = 'button';
                removeButton.className = 'tag-input-chip__remove';
                removeButton.setAttribute('aria-label', 'Убрать группу «' + groupName + '»');
                removeButton.innerHTML = '&times;';
                removeButton.addEventListener('click', function (event) {
                    event.preventDefault();
                    checkbox.checked = false;
                    checkbox.dispatchEvent(new Event('change', { bubbles: true }));
                    renderChips();
                });

                chip.appendChild(label);
                chip.appendChild(removeButton);
                chipsContainer.appendChild(chip);
            });
            updatePickButtons();
            filterExistingGroups();
        }

        function updatePickButtons() {
            var ids = selectedIds(widget);
            widget.querySelectorAll('.group-picker-pick').forEach(function (button) {
                var groupId = button.dataset.groupId || '';
                var selected = ids.indexOf(groupId) !== -1;
                button.classList.toggle('tag-input-pick--selected', selected);
                button.setAttribute('aria-pressed', selected ? 'true' : 'false');
            });
        }

        function groupMatchesQuery(button, query) {
            var groupName = (button.dataset.groupName || '').toLowerCase();
            return groupName.indexOf(query) !== -1;
        }

        function filterExistingGroups() {
            var query = typingInput.value.trim().toLowerCase();
            var visibleCount = 0;
            var isFiltering = query.length > 0;
            var ids = selectedIds(widget);
            var hasSections = Boolean(widget.querySelector('.group-picker-section'));

            if (existingBlock) {
                existingBlock.classList.toggle('tag-input-existing--filtered', isFiltering);
            }
            if (existingLabel && !hasSections) {
                existingLabel.textContent = isFiltering ? 'Подходящие группы' : 'Доступные группы';
            }
            if (existingHint && !hasSections) {
                existingHint.textContent = isFiltering ? 'Enter — выбрать первую' : 'нажмите, чтобы добавить';
            }

            widget.querySelectorAll('.group-picker-pick').forEach(function (button) {
                var groupId = button.dataset.groupId || '';
                var selected = ids.indexOf(groupId) !== -1;
                var matches = !isFiltering || groupMatchesQuery(button, query);
                // Selected groups live in the composer; hide them from the picker.
                var visible = matches && !selected;
                button.hidden = !visible;
                button.classList.toggle('tag-input-pick--selected', selected);
                if (visible) {
                    visibleCount += 1;
                }
            });

            if (hasSections) {
                widget.querySelectorAll('.group-picker-section').forEach(function (section) {
                    var anyVisible = section.querySelector('.group-picker-pick:not([hidden])');
                    section.hidden = !anyVisible;
                });
            }

            if (emptyMessage) {
                emptyMessage.hidden = visibleCount > 0;
            }
        }

        function firstVisiblePick() {
            return widget.querySelector('.group-picker-pick:not([hidden])');
        }

        function addGroup(groupId) {
            var checkbox = findCheckbox(widget, groupId);
            if (!checkbox || checkbox.checked) {
                return false;
            }
            checkbox.checked = true;
            checkbox.dispatchEvent(new Event('change', { bubbles: true }));
            renderChips();
            return true;
        }

        composer.addEventListener('click', function () {
            typingInput.focus();
        });

        widget.querySelectorAll('.group-picker-pick').forEach(function (button) {
            button.addEventListener('mousedown', function (event) {
                event.preventDefault();
            });
            button.addEventListener('click', function () {
                addGroup(button.dataset.groupId || '');
                typingInput.value = '';
                typingInput.focus();
            });
        });

        typingInput.addEventListener('input', filterExistingGroups);

        typingInput.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                typingInput.value = '';
                filterExistingGroups();
                return;
            }
            if (event.key === 'Backspace' && !typingInput.value) {
                var checked = getCheckboxes(widget).filter(function (checkbox) { return checkbox.checked; });
                if (!checked.length) {
                    return;
                }
                checked[checked.length - 1].checked = false;
                checked[checked.length - 1].dispatchEvent(new Event('change', { bubbles: true }));
                renderChips();
                event.preventDefault();
                return;
            }
            if (event.key !== 'Enter') {
                return;
            }
            event.preventDefault();
            var firstPick = firstVisiblePick();
            if (firstPick) {
                addGroup(firstPick.dataset.groupId || '');
                typingInput.value = '';
                filterExistingGroups();
            }
        });

        renderChips();
    }

    function initWithin(root) {
        (root || document).querySelectorAll('.group-picker-widget').forEach(initWidget);
    }

    window.GroupPicker = {
        init: initWidget,
        initWithin: initWithin,
    };

    document.addEventListener('DOMContentLoaded', function () {
        initWithin(document);
    });
})();
