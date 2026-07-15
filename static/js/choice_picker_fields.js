(function () {
    'use strict';

    var openPicker = null;

    function getMenu(wrap) {
        return wrap ? wrap._choiceMenu || wrap.querySelector('.choice-picker__menu') : null;
    }

    function positionMenu(wrap) {
        var trigger = wrap.querySelector('.choice-picker__trigger');
        var menu = getMenu(wrap);
        if (!trigger || !menu) {
            return;
        }
        var rect = trigger.getBoundingClientRect();
        var menuHeight = menu.scrollHeight;
        var spaceBelow = window.innerHeight - rect.bottom - 8;
        var spaceAbove = rect.top - 8;
        var openUp = spaceBelow < Math.min(menuHeight, 224) && spaceAbove > spaceBelow;
        var maxHeight = Math.max(120, Math.min(224, openUp ? spaceAbove : spaceBelow));
        var width = Math.max(rect.width, 180);

        menu.style.position = 'fixed';
        menu.style.left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8)) + 'px';
        menu.style.width = width + 'px';
        menu.style.maxHeight = maxHeight + 'px';
        menu.style.zIndex = '1080';

        if (openUp) {
            menu.style.top = 'auto';
            menu.style.bottom = (window.innerHeight - rect.top + 6) + 'px';
        } else {
            menu.style.bottom = 'auto';
            menu.style.top = (rect.bottom + 6) + 'px';
        }
    }

    function closePicker(wrap) {
        if (!wrap) {
            return;
        }
        wrap.classList.remove('is-open');
        var trigger = wrap.querySelector('.choice-picker__trigger');
        if (trigger) {
            trigger.setAttribute('aria-expanded', 'false');
        }
        var menu = getMenu(wrap);
        if (menu) {
            menu.hidden = true;
        }
        if (openPicker === wrap) {
            openPicker = null;
        }
    }

    function openMenu(wrap) {
        closeAll(wrap);
        var menu = getMenu(wrap);
        var trigger = wrap.querySelector('.choice-picker__trigger');
        if (!menu || !trigger) {
            return;
        }
        if (menu.parentNode !== document.body) {
            document.body.appendChild(menu);
            wrap._choiceMenu = menu;
        }
        menu.hidden = false;
        wrap.classList.add('is-open');
        trigger.setAttribute('aria-expanded', 'true');
        openPicker = wrap;
        positionMenu(wrap);
    }

    function closeAll(except) {
        document.querySelectorAll('.choice-picker.is-open').forEach(function (wrap) {
            if (wrap !== except) {
                closePicker(wrap);
            }
        });
    }

    function selectedLabel(select) {
        if (!select || !select.value) {
            return '';
        }
        var option = select.options[select.selectedIndex];
        return option ? option.textContent.trim() : '';
    }

    function syncPicker(select) {
        var wrap = select.closest('.choice-picker');
        if (!wrap) {
            return;
        }
        var valueNode = wrap.querySelector('.choice-picker__value');
        var label = selectedLabel(select);
        if (valueNode) {
            valueNode.textContent = label || 'Выберите значение';
            valueNode.classList.toggle('is-placeholder', !label);
        }
        var selectedValue = select.value || '';
        var menu = getMenu(wrap);
        if (!menu) {
            return;
        }
        menu.querySelectorAll('.choice-picker__option').forEach(function (button) {
            var isSelected = button.dataset.value === selectedValue;
            button.classList.toggle('is-selected', isSelected);
            button.setAttribute('aria-selected', isSelected ? 'true' : 'false');
        });
    }

    function enhanceSelect(select) {
        if (!select || select.dataset.choicePickerBound === 'true') {
            syncPicker(select);
            return;
        }
        select.dataset.choicePickerBound = 'true';

        var wrap = document.createElement('div');
        wrap.className = 'choice-picker';
        select.parentNode.insertBefore(wrap, select);
        wrap.appendChild(select);
        select.classList.add('choice-picker__native');

        var trigger = document.createElement('button');
        trigger.type = 'button';
        trigger.className = 'choice-picker__trigger';
        trigger.setAttribute('aria-haspopup', 'listbox');
        trigger.setAttribute('aria-expanded', 'false');

        var valueNode = document.createElement('span');
        valueNode.className = 'choice-picker__value is-placeholder';
        trigger.appendChild(valueNode);

        var chevron = document.createElement('span');
        chevron.className = 'choice-picker__chevron';
        chevron.setAttribute('aria-hidden', 'true');
        trigger.appendChild(chevron);
        wrap.appendChild(trigger);

        var menu = document.createElement('div');
        menu.className = 'choice-picker__menu';
        menu.setAttribute('role', 'listbox');
        menu.hidden = true;
        wrap.appendChild(menu);
        wrap._choiceMenu = menu;

        Array.from(select.options || []).forEach(function (option) {
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'choice-picker__option';
            button.dataset.value = option.value;
            button.setAttribute('role', 'option');
            button.setAttribute('aria-selected', 'false');

            var label = document.createElement('span');
            label.className = 'choice-picker__option-label';
            label.textContent = option.value
                ? option.textContent.trim()
                : '— не выбрано —';
            button.appendChild(label);

            if (option.value) {
                var check = document.createElement('span');
                check.className = 'choice-picker__check';
                check.setAttribute('aria-hidden', 'true');
                check.textContent = '✓';
                button.appendChild(check);
            }

            button.addEventListener('click', function () {
                select.value = option.value;
                select.dispatchEvent(new Event('change', { bubbles: true }));
                syncPicker(select);
                closePicker(wrap);
                trigger.focus();
            });
            menu.appendChild(button);
        });

        trigger.addEventListener('click', function () {
            if (wrap.classList.contains('is-open')) {
                closePicker(wrap);
            } else {
                openMenu(wrap);
            }
        });

        select.addEventListener('change', function () {
            syncPicker(select);
        });
        syncPicker(select);
    }

    function initChoicePickerFields(root) {
        var scope = root || document;
        scope.querySelectorAll('select[data-choice-picker]').forEach(enhanceSelect);
    }

    document.addEventListener('click', function (event) {
        if (!openPicker) {
            return;
        }
        var menu = getMenu(openPicker);
        var inTrigger = openPicker.contains(event.target);
        var inMenu = menu && menu.contains(event.target);
        if (!inTrigger && !inMenu) {
            closePicker(openPicker);
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && openPicker) {
            var trigger = openPicker.querySelector('.choice-picker__trigger');
            closePicker(openPicker);
            if (trigger) {
                trigger.focus();
            }
        }
    });

    window.addEventListener('resize', function () {
        if (openPicker) {
            positionMenu(openPicker);
        }
    });

    window.addEventListener('scroll', function () {
        if (openPicker) {
            positionMenu(openPicker);
        }
    }, true);

    window.ChoicePickerFields = {
        init: initChoicePickerFields,
        syncSelect: syncPicker,
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            initChoicePickerFields();
        });
    } else {
        initChoicePickerFields();
    }
})();
