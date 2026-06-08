(function () {
    'use strict';

    function parseTags(value) {
        return (value || '')
            .split(',')
            .map(function (part) { return part.trim(); })
            .filter(Boolean);
    }

    function getCurrentToken(value) {
        var parts = (value || '').split(',');
        return parts[parts.length - 1].trim();
    }

    function tagAlreadySelected(input, tagName) {
        var selected = parseTags(input.value).map(function (name) {
            return name.toLowerCase();
        });
        return selected.indexOf(tagName.toLowerCase()) !== -1;
    }

    function applyTagName(input, tagName) {
        if (tagAlreadySelected(input, tagName)) {
            return;
        }

        var value = input.value || '';
        var parts = value.split(',');
        var lastIndex = parts.length - 1;
        var lastPart = parts[lastIndex].trim();

        if (!value.trim()) {
            input.value = tagName;
        } else if (lastPart === '' || value.trim().endsWith(',')) {
            input.value = value.replace(/\s*,\s*$/, '') + ', ' + tagName;
        } else {
            parts[lastIndex] = ' ' + tagName;
            input.value = parts
                .map(function (part) { return part.trim(); })
                .filter(Boolean)
                .join(', ');
        }

        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.focus();
    }

    function filterSuggestions(allTags, token) {
        var query = token.toLowerCase();
        if (!query) {
            return allTags.slice(0, 8);
        }
        return allTags.filter(function (tag) {
            return tag.name.toLowerCase().indexOf(query) !== -1
                || tag.slug.toLowerCase().indexOf(query) !== -1;
        }).slice(0, 8);
    }

    function renderDropdown(widget, input, dropdown, suggestions) {
        var token = getCurrentToken(input.value);
        var matches = filterSuggestions(suggestions, token);

        dropdown.innerHTML = '';
        if (!matches.length || (!token && !input.matches(':focus'))) {
            dropdown.hidden = true;
            return;
        }

        matches.forEach(function (tag) {
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'tag-input-dropdown__item';
            button.setAttribute('role', 'option');
            button.dataset.tagName = tag.name;
            button.innerHTML = '<span class="tag-input-dropdown__name">' + tag.name + '</span>'
                + '<span class="tag-input-dropdown__hint">использовать это название</span>';
            button.addEventListener('mousedown', function (event) {
                event.preventDefault();
            });
            button.addEventListener('click', function () {
                applyTagName(input, tag.name);
                dropdown.hidden = true;
            });
            dropdown.appendChild(button);
        });
        dropdown.hidden = false;
    }

    function markUsedSuggestions(widget, input) {
        var selected = parseTags(input.value).map(function (name) {
            return name.toLowerCase();
        });
        widget.querySelectorAll('.tag-input-pick').forEach(function (button) {
            var tagName = (button.dataset.tagName || '').toLowerCase();
            button.classList.toggle('tag-input-pick--selected', selected.indexOf(tagName) !== -1);
        });
    }

    function initWidget(widget) {
        var input = widget.querySelector('.tag-input-field');
        var dropdown = widget.querySelector('.tag-input-dropdown');
        if (!input || !dropdown) {
            return;
        }

        var suggestions = [];
        try {
            suggestions = JSON.parse(widget.dataset.tagSuggestions || '[]');
        } catch (error) {
            suggestions = [];
        }

        widget.querySelectorAll('.tag-input-pick').forEach(function (button) {
            button.addEventListener('click', function () {
                applyTagName(input, button.dataset.tagName || '');
                markUsedSuggestions(widget, input);
            });
        });

        input.addEventListener('focus', function () {
            renderDropdown(widget, input, dropdown, suggestions);
        });

        input.addEventListener('input', function () {
            renderDropdown(widget, input, dropdown, suggestions);
            markUsedSuggestions(widget, input);
        });

        input.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                dropdown.hidden = true;
                return;
            }
            if (event.key !== 'Enter' || dropdown.hidden) {
                return;
            }
            var firstItem = dropdown.querySelector('.tag-input-dropdown__item');
            if (!firstItem) {
                return;
            }
            event.preventDefault();
            applyTagName(input, firstItem.dataset.tagName || '');
            dropdown.hidden = true;
            markUsedSuggestions(widget, input);
        });

        input.addEventListener('blur', function () {
            window.setTimeout(function () {
                dropdown.hidden = true;
            }, 120);
        });

        markUsedSuggestions(widget, input);
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.tag-input-widget').forEach(initWidget);
    });
})();
