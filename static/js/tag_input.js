(function () {
    'use strict';

    var SCOPED_SEPARATOR = '::';

    function escapeHtml(value) {
        return (value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function isScopedTagName(tagName) {
        var normalized = (tagName || '').trim();
        var separatorIndex = normalized.lastIndexOf(SCOPED_SEPARATOR);
        if (separatorIndex === -1) {
            return false;
        }
        var scope = normalized.slice(0, separatorIndex).trim();
        var value = normalized.slice(separatorIndex + SCOPED_SEPARATOR.length).trim();
        return Boolean(scope && value);
    }

    function renderScopedTagLabel(tagName) {
        var normalized = (tagName || '').trim();
        var separatorIndex = normalized.lastIndexOf(SCOPED_SEPARATOR);
        if (separatorIndex === -1) {
            return '<span class="entity-tag__text">' + escapeHtml(normalized) + '</span>';
        }
        var scope = normalized.slice(0, separatorIndex).trim();
        var value = normalized.slice(separatorIndex + SCOPED_SEPARATOR.length).trim();
        if (!scope || !value) {
            return '<span class="entity-tag__text">' + escapeHtml(normalized) + '</span>';
        }
        return (
            '<span class="entity-tag__text">' + escapeHtml(scope) + '</span>' +
            '<span class="entity-tag__text-scoped">' + escapeHtml(value) + '</span>'
        );
    }

    function parseTags(value) {
        return (value || '')
            .split(/[,;]+/)
            .map(function (part) { return part.trim(); })
            .filter(Boolean);
    }

    function tagIndex(tags, tagName) {
        var target = tagName.toLowerCase();
        for (var i = 0; i < tags.length; i += 1) {
            if (tags[i].toLowerCase() === target) {
                return i;
            }
        }
        return -1;
    }

    function tagScopeKey(tagName) {
        var normalized = (tagName || '').trim();
        var separatorIndex = normalized.indexOf(SCOPED_SEPARATOR);
        if (separatorIndex === -1) {
            return null;
        }
        var scope = normalized.slice(0, separatorIndex).trim();
        return scope ? scope.toLowerCase() : null;
    }

    function contrastTextColor(hexColor) {
        var raw = (hexColor || '').replace('#', '');
        if (raw.length !== 6) {
            return '#212529';
        }
        var red = parseInt(raw.slice(0, 2), 16);
        var green = parseInt(raw.slice(2, 4), 16);
        var blue = parseInt(raw.slice(4, 6), 16);
        var luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255;
        return luminance > 0.6 ? '#212529' : '#ffffff';
    }

    function buildSuggestionMap(widget) {
        var map = Object.create(null);
        var scriptId = widget.getAttribute('data-tag-suggestions-id');
        var scriptEl = scriptId ? document.getElementById(scriptId) : null;
        var raw = scriptEl ? scriptEl.textContent : widget.getAttribute('data-tag-suggestions');
        if (!raw) {
            return map;
        }
        try {
            var suggestions = JSON.parse(raw);
            suggestions.forEach(function (item) {
                if (!item || !item.name) {
                    return;
                }
                map[item.name.toLowerCase()] = item;
            });
        } catch (error) {
            return map;
        }
        return map;
    }

    function applyTagVisual(element, tagName, suggestionMap) {
        var meta = suggestionMap[(tagName || '').toLowerCase()] || null;
        var color = (meta && meta.color) || element.dataset.tagColor || '';
        var description = (meta && meta.description) || element.dataset.tagDescription || '';
        element.classList.toggle('tone-tag', !color);
        if (color) {
            var textColor = contrastTextColor(color);
            element.style.setProperty('--label-background-color', color);
            element.style.setProperty('--label-text-color', textColor);
        } else {
            element.style.removeProperty('--label-background-color');
            element.style.removeProperty('--label-text-color');
        }
        if (description) {
            element.title = description;
        }
    }

    function initPickButtonStyles(widget, suggestionMap) {
        widget.querySelectorAll('.tag-input-pick').forEach(function (button) {
            var tagName = button.dataset.tagName || '';
            button.classList.toggle('entity-tag--scoped', isScopedTagName(tagName));
            applyTagVisual(button, tagName, suggestionMap);
            var description = button.dataset.tagDescription || '';
            if (description) {
                button.title = description;
            }
        });
    }

    function initWidget(widget) {
        var hiddenInput = widget.querySelector('.tag-input-value');
        var typingInput = widget.querySelector('.tag-input-typing');
        var chipsContainer = widget.querySelector('.tag-input-chips');
        var composer = widget.querySelector('.tag-input-composer');
        var existingBlock = widget.querySelector('.tag-input-existing');
        var existingLabel = widget.querySelector('.tag-input-existing__label');
        var emptyMessage = widget.querySelector('.tag-input-existing__empty');
        if (!hiddenInput || !typingInput || !chipsContainer || !composer) {
            return;
        }

        var suggestionMap = buildSuggestionMap(widget);
        var tags = parseTags(hiddenInput.value);

        function syncHidden() {
            hiddenInput.value = tags.join(', ');
            hiddenInput.dispatchEvent(new Event('input', { bubbles: true }));
            hiddenInput.dispatchEvent(new Event('change', { bubbles: true }));
        }

        function removeScopedConflict(tagName) {
            var scopeKey = tagScopeKey(tagName);
            if (!scopeKey) {
                return;
            }
            for (var i = tags.length - 1; i >= 0; i -= 1) {
                if (tagScopeKey(tags[i]) === scopeKey && tags[i].toLowerCase() !== tagName.toLowerCase()) {
                    tags.splice(i, 1);
                }
            }
        }

        function renderChips() {
            chipsContainer.innerHTML = '';
            tags.forEach(function (tagName) {
                var chip = document.createElement('span');
                chip.className = 'tag-input-chip entity-tag' + (isScopedTagName(tagName) ? ' entity-tag--scoped' : '');
                chip.dataset.tagName = tagName;
                applyTagVisual(chip, tagName, suggestionMap);

                var label = document.createElement('span');
                label.className = 'tag-input-chip__label';
                label.innerHTML = renderScopedTagLabel(tagName);

                var removeButton = document.createElement('button');
                removeButton.type = 'button';
                removeButton.className = 'tag-input-chip__remove';
                removeButton.setAttribute('aria-label', 'Убрать тег «' + tagName + '»');
                removeButton.innerHTML = '&times;';
                removeButton.addEventListener('click', function (event) {
                    event.preventDefault();
                    removeTag(tagName);
                });

                chip.appendChild(label);
                chip.appendChild(removeButton);
                chipsContainer.appendChild(chip);
            });
            updatePickButtons();
            filterExistingTags();
        }

        function updatePickButtons() {
            widget.querySelectorAll('.tag-input-pick').forEach(function (button) {
                var tagName = button.dataset.tagName || '';
                var selected = tagIndex(tags, tagName) !== -1;
                button.classList.toggle('tag-input-pick--selected', selected);
                button.setAttribute('aria-pressed', selected ? 'true' : 'false');
                applyTagVisual(button, tagName, suggestionMap);
            });
        }

        function tagMatchesQuery(button, query) {
            var tagName = (button.dataset.tagName || '').toLowerCase();
            var tagSlug = (button.dataset.tagSlug || '').toLowerCase();
            return tagName.indexOf(query) !== -1 || tagSlug.indexOf(query) !== -1;
        }

        function filterExistingTags() {
            var query = typingInput.value.trim().toLowerCase();
            var visibleCount = 0;
            var isFiltering = query.length > 0;

            if (existingBlock) {
                existingBlock.classList.toggle('tag-input-existing--filtered', isFiltering);
            }
            if (existingLabel) {
                existingLabel.textContent = isFiltering ? 'Похожие теги' : 'Существующие теги';
            }

            widget.querySelectorAll('.tag-input-pick').forEach(function (button) {
                var tagName = button.dataset.tagName || '';
                var visible;
                if (!isFiltering) {
                    visible = true;
                } else {
                    visible = tagMatchesQuery(button, query) && tagIndex(tags, tagName) === -1;
                }
                button.hidden = !visible;
                if (visible) {
                    visibleCount += 1;
                }
            });

            if (emptyMessage) {
                emptyMessage.hidden = !isFiltering || visibleCount > 0;
            }
        }

        function firstVisiblePick() {
            return widget.querySelector('.tag-input-pick:not([hidden])');
        }

        function addTag(tagName) {
            var normalized = (tagName || '').trim();
            if (!normalized || tagIndex(tags, normalized) !== -1) {
                return false;
            }
            removeScopedConflict(normalized);
            tags.push(normalized);
            syncHidden();
            renderChips();
            return true;
        }

        function removeTag(tagName) {
            var index = tagIndex(tags, tagName);
            if (index === -1) {
                return false;
            }
            tags.splice(index, 1);
            syncHidden();
            renderChips();
            return true;
        }

        function commitTyping() {
            var token = typingInput.value.trim();
            if (!token) {
                return false;
            }
            var added = addTag(token);
            typingInput.value = '';
            filterExistingTags();
            return added;
        }

        composer.addEventListener('click', function () {
            typingInput.focus();
        });

        widget.querySelectorAll('.tag-input-pick').forEach(function (button) {
            button.addEventListener('mousedown', function (event) {
                event.preventDefault();
            });
            button.addEventListener('click', function () {
                var tagName = button.dataset.tagName || '';
                if (tagIndex(tags, tagName) === -1) {
                    removeScopedConflict(tagName);
                    addTag(tagName);
                    typingInput.value = '';
                    filterExistingTags();
                } else {
                    removeTag(tagName);
                }
                typingInput.focus();
            });
        });

        typingInput.addEventListener('input', filterExistingTags);

        typingInput.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                typingInput.value = '';
                filterExistingTags();
                return;
            }
            if (event.key === 'Backspace' && !typingInput.value && tags.length) {
                removeTag(tags[tags.length - 1]);
                event.preventDefault();
                return;
            }
            if (event.key === ',' || event.key === ';') {
                event.preventDefault();
                commitTyping();
                return;
            }
            if (event.key !== 'Enter') {
                return;
            }
            event.preventDefault();
            var token = typingInput.value.trim();
            if (!token) {
                return;
            }
            var firstPick = firstVisiblePick();
            if (firstPick && typingInput.value.trim()) {
                var pickName = firstPick.dataset.tagName || '';
                removeScopedConflict(pickName);
                addTag(pickName);
                typingInput.value = '';
                filterExistingTags();
                return;
            }
            commitTyping();
        });

        typingInput.addEventListener('blur', function () {
            window.setTimeout(function () {
                if (widget.contains(document.activeElement)) {
                    return;
                }
                commitTyping();
            }, 120);
        });

        initPickButtonStyles(widget, suggestionMap);
        renderChips();
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.tag-input-widget').forEach(initWidget);
    });
})();
