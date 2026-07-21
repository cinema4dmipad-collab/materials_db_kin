(function () {
    'use strict';

    var SCOPED_SEPARATOR = '::';
    var SCOPED_TAG_DEFAULT_COLOR = '#007679';

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
        if (!color && isScopedTagName(tagName)) {
            // Совпадает с coalesce_tags_for_display / списком материалов
            color = SCOPED_TAG_DEFAULT_COLOR;
        }
        element.classList.toggle('tone-tag', !color);
        element.classList.toggle('entity-tag--scoped', isScopedTagName(tagName));
        if (color) {
            var textColor = contrastTextColor(color);
            element.style.setProperty('--label-background-color', color);
            element.style.setProperty('--label-text-color', textColor);
            element.dataset.tagColor = color;
        } else {
            element.style.removeProperty('--label-background-color');
            element.style.removeProperty('--label-text-color');
            delete element.dataset.tagColor;
        }
        if (description) {
            element.title = description;
            element.dataset.tagDescription = description;
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
        var renderedTagKeys = null;

        function tagKey(tagName) {
            return String(tagName || '').trim().toLowerCase();
        }

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

        function playChipEnter(chip) {
            // Opacity/slide only — scale makes scoped pills look square for a frame.
            chip.classList.add('tag-input-chip--animating');
            chip.style.opacity = '0';
            chip.style.transform = 'translateY(4px)';

            window.requestAnimationFrame(function () {
                window.requestAnimationFrame(function () {
                    if (typeof chip.animate === 'function') {
                        var animation = chip.animate(
                            [
                                { opacity: 0, transform: 'translateY(4px)' },
                                { opacity: 1, transform: 'translateY(0)' },
                            ],
                            {
                                duration: 320,
                                easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
                                fill: 'forwards',
                            }
                        );
                        animation.addEventListener('finish', function () {
                            chip.style.opacity = '';
                            chip.style.transform = '';
                            chip.classList.remove('tag-input-chip--animating');
                        });
                        return;
                    }

                    chip.classList.add('tag-input-chip--enter');
                    chip.style.opacity = '';
                    chip.style.transform = '';
                    window.setTimeout(function () {
                        chip.classList.remove('tag-input-chip--enter');
                        chip.classList.remove('tag-input-chip--animating');
                    }, 320);
                });
            });
        }

        function createChip(tagName) {
            var chip = document.createElement('span');
            chip.className = 'tag-input-chip entity-tag' + (isScopedTagName(tagName) ? ' entity-tag--scoped' : '');
            chip.dataset.tagName = tagName;
            applyTagVisual(chip, tagName, suggestionMap);
            // Same GlLabel markup as picker/badges — text parts are direct children.
            chip.innerHTML = renderScopedTagLabel(tagName);

            var removeButton = document.createElement('button');
            removeButton.type = 'button';
            removeButton.className = 'tag-input-chip__remove';
            removeButton.setAttribute('aria-label', 'Убрать тег «' + tagName + '»');
            removeButton.innerHTML = '&times;';
            removeButton.addEventListener('click', function (event) {
                event.preventDefault();
                removeTag(tagName);
            });

            chip.appendChild(removeButton);
            return chip;
        }

        function renderChips() {
            var previousKeys = renderedTagKeys;
            var animateNew = previousKeys !== null;
            var existingByKey = Object.create(null);

            Array.prototype.forEach.call(
                chipsContainer.querySelectorAll('.tag-input-chip'),
                function (chip) {
                    existingByKey[tagKey(chip.dataset.tagName)] = chip;
                }
            );

            var nextKeys = Object.create(null);
            tags.forEach(function (tagName) {
                var key = tagKey(tagName);
                nextKeys[key] = true;
                var existing = existingByKey[key];
                if (existing) {
                    chipsContainer.appendChild(existing);
                    delete existingByKey[key];
                    return;
                }
                var chip = createChip(tagName);
                chipsContainer.appendChild(chip);
                if (animateNew) {
                    playChipEnter(chip);
                }
            });

            Object.keys(existingByKey).forEach(function (key) {
                existingByKey[key].remove();
            });

            renderedTagKeys = nextKeys;
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

        function normalizeSearchText(value) {
            return String(value || '')
                .toLowerCase()
                .replace(/::/g, ' ')
                .replace(/--/g, ' ')
                .replace(/\s+/g, ' ')
                .trim();
        }

        function splitTagParts(tagName) {
            var normalized = String(tagName || '').trim();
            var separatorIndex = normalized.lastIndexOf(SCOPED_SEPARATOR);
            if (separatorIndex === -1) {
                return { scope: '', value: '', plain: normalized };
            }
            var scope = normalized.slice(0, separatorIndex).trim();
            var value = normalized.slice(separatorIndex + SCOPED_SEPARATOR.length).trim();
            if (!scope || !value) {
                return { scope: '', value: '', plain: normalized };
            }
            return { scope: scope, value: value, plain: normalized };
        }

        // Match at start of haystack or start of a word — never mid-word / UI titles.
        function startsAtWord(haystack, query) {
            var normalizedHaystack = normalizeSearchText(haystack);
            var normalizedQuery = normalizeSearchText(query);
            if (!normalizedQuery || !normalizedHaystack) {
                return false;
            }
            if (normalizedHaystack.indexOf(normalizedQuery) === 0) {
                return true;
            }
            return normalizedHaystack.indexOf(' ' + normalizedQuery) !== -1;
        }

        function scoreTagMatch(button, query) {
            var normalizedQuery = normalizeSearchText(query);
            if (!normalizedQuery) {
                return 0;
            }
            var tagName = button.dataset.tagName || '';
            var tagSlug = button.dataset.tagSlug || '';
            var description = button.dataset.tagDescription || '';
            var parts = splitTagParts(tagName);
            var nameNorm = normalizeSearchText(tagName);
            var slugNorm = normalizeSearchText(tagSlug);
            var scopeNorm = normalizeSearchText(parts.scope);
            var valueNorm = normalizeSearchText(parts.value);
            var plainNorm = normalizeSearchText(parts.plain);
            var descNorm = normalizeSearchText(description);

            if (nameNorm === normalizedQuery || plainNorm === normalizedQuery) {
                return 100;
            }
            if (valueNorm === normalizedQuery || scopeNorm === normalizedQuery) {
                return 95;
            }
            if (nameNorm.indexOf(normalizedQuery) === 0 || plainNorm.indexOf(normalizedQuery) === 0) {
                return 90;
            }
            if (valueNorm.indexOf(normalizedQuery) === 0) {
                return 85;
            }
            if (scopeNorm.indexOf(normalizedQuery) === 0) {
                return 80;
            }
            if (slugNorm.indexOf(normalizedQuery) === 0) {
                return 75;
            }
            if (startsAtWord(valueNorm, normalizedQuery)) {
                return 60;
            }
            if (startsAtWord(nameNorm, normalizedQuery) || startsAtWord(plainNorm, normalizedQuery)) {
                return 50;
            }
            if (startsAtWord(scopeNorm, normalizedQuery)) {
                return 40;
            }
            if (startsAtWord(slugNorm, normalizedQuery)) {
                return 30;
            }
            if (descNorm && startsAtWord(descNorm, normalizedQuery)) {
                return 10;
            }
            return 0;
        }

        function dedupePickButtons() {
            var seen = Object.create(null);
            widget.querySelectorAll('.tag-input-pick').forEach(function (button) {
                var key = tagKey(button.dataset.tagName || button.dataset.tagSlug || '');
                if (!key) {
                    return;
                }
                if (seen[key]) {
                    button.remove();
                    return;
                }
                seen[key] = true;
            });
        }

        function filterExistingTags() {
            var query = typingInput.value.trim();
            var isFiltering = query.length > 0;
            var list = widget.querySelector('.tag-input-existing__list');
            var matched = [];

            if (existingBlock) {
                existingBlock.classList.toggle('tag-input-existing--filtered', isFiltering);
            }
            if (existingLabel) {
                existingLabel.textContent = isFiltering ? 'Похожие теги' : 'Существующие теги';
            }

            widget.querySelectorAll('.tag-input-pick').forEach(function (button, index) {
                var tagName = button.dataset.tagName || '';
                var selected = tagIndex(tags, tagName) !== -1;
                var score = isFiltering ? scoreTagMatch(button, query) : 1;
                button.classList.remove('tag-input-pick--already-selected');
                button.removeAttribute('data-tag-match-score');
                if (score <= 0) {
                    button.hidden = true;
                    return;
                }
                matched.push({
                    button: button,
                    selected: selected,
                    score: score,
                    index: index,
                });
            });

            if (isFiltering) {
                matched.sort(function (left, right) {
                    if (left.selected !== right.selected) {
                        return left.selected ? 1 : -1;
                    }
                    if (right.score !== left.score) {
                        return right.score - left.score;
                    }
                    return left.index - right.index;
                });
            }

            var hasUnselectedMatch = matched.some(function (item) { return !item.selected; });
            var visibleCount = 0;
            matched.forEach(function (item) {
                var hideSelected = isFiltering && hasUnselectedMatch && item.selected;
                item.button.hidden = hideSelected;
                if (hideSelected) {
                    return;
                }
                if (isFiltering) {
                    item.button.dataset.tagMatchScore = String(item.score);
                    if (item.selected) {
                        item.button.classList.add('tag-input-pick--already-selected');
                    }
                    if (list) {
                        list.appendChild(item.button);
                    }
                }
                visibleCount += 1;
            });

            if (emptyMessage) {
                emptyMessage.hidden = !isFiltering || visibleCount > 0;
            }
        }

        function firstVisiblePick() {
            var visible = Array.prototype.slice.call(
                widget.querySelectorAll('.tag-input-pick:not([hidden])')
            );
            if (!visible.length) {
                return null;
            }
            visible.sort(function (left, right) {
                var leftSelected = left.classList.contains('tag-input-pick--selected') ? 1 : 0;
                var rightSelected = right.classList.contains('tag-input-pick--selected') ? 1 : 0;
                if (leftSelected !== rightSelected) {
                    return leftSelected - rightSelected;
                }
                var leftScore = Number(left.dataset.tagMatchScore || 0);
                var rightScore = Number(right.dataset.tagMatchScore || 0);
                return rightScore - leftScore;
            });
            return visible[0];
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

        dedupePickButtons();

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
        typingInput.addEventListener('compositionend', filterExistingTags);

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
        widget.dataset.tagInputReady = '1';
    }

    function bootTagInputs() {
        document.querySelectorAll('.tag-input-widget:not([data-tag-input-ready])').forEach(initWidget);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootTagInputs);
    } else {
        bootTagInputs();
    }
})();
