(function () {
    'use strict';

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

        var tags = parseTags(hiddenInput.value);

        function syncHidden() {
            hiddenInput.value = tags.join(', ');
            hiddenInput.dispatchEvent(new Event('input', { bubbles: true }));
            hiddenInput.dispatchEvent(new Event('change', { bubbles: true }));
        }

        function renderChips() {
            chipsContainer.innerHTML = '';
            tags.forEach(function (tagName) {
                var chip = document.createElement('span');
                chip.className = 'tag-input-chip entity-tag tone-tag';
                chip.dataset.tagName = tagName;

                var label = document.createElement('span');
                label.className = 'tag-input-chip__label';
                label.textContent = tagName;

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
                addTag(firstPick.dataset.tagName || '');
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

        renderChips();
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.tag-input-widget').forEach(initWidget);
    });
})();
