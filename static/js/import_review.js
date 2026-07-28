(function () {
    'use strict';

    var board = document.getElementById('import-review-board');
    if (!board) {
        return;
    }

    var reviewUrl = board.getAttribute('data-review-url') || '';
    var csrf = board.getAttribute('data-csrf') || '';
    var dragCard = null;
    var activeZone = null;

    var COLUMN_META = {
        approved: {
            emptyAttr: 'data-empty-approved',
            emptyText: 'Нет материалов со статусом «утвержден».',
            countId: 'import-review-approved-count',
        },
        verified: {
            emptyAttr: 'data-empty-verified',
            emptyText: 'Перетащите сюда проверенные материалы.',
            countId: 'import-review-verified-count',
        },
    };

    function columnBody(column) {
        return board.querySelector('[data-drop-zone="' + column + '"] .import-review-column__body');
    }

    function zoneFromEvent(event) {
        var el = event.target;
        if (!el || !el.closest) {
            return null;
        }
        return el.closest('[data-drop-zone]');
    }

    function setActiveZone(zone) {
        if (activeZone === zone) {
            return;
        }
        board.querySelectorAll('.is-drop-target').forEach(function (el) {
            el.classList.remove('is-drop-target');
        });
        activeZone = zone || null;
        if (activeZone) {
            activeZone.classList.add('is-drop-target');
        }
    }

    function updateCounts() {
        Object.keys(COLUMN_META).forEach(function (column) {
            var meta = COLUMN_META[column];
            var count = board.querySelectorAll(
                '[data-drop-zone="' + column + '"] .import-review-card'
            ).length;
            var badge = document.getElementById(meta.countId);
            if (badge) {
                badge.textContent = String(count);
            }
            toggleEmpty(columnBody(column), meta.emptyAttr, count === 0, meta.emptyText);
        });
    }

    function toggleEmpty(zone, attr, show, text) {
        if (!zone) {
            return;
        }
        var empty = zone.querySelector('[' + attr + ']');
        if (show) {
            if (!empty) {
                empty = document.createElement('p');
                empty.className = 'import-review-empty text-muted small mb-0';
                empty.setAttribute(attr, '');
                empty.textContent = text;
                zone.appendChild(empty);
            }
        } else if (empty) {
            empty.remove();
        }
    }

    function setCardStatus(card, column) {
        card.setAttribute('data-status', column);
    }

    function moveCard(card, column) {
        var zone = columnBody(column);
        if (!zone || !card) {
            return;
        }
        var empty = zone.querySelector('[data-empty-approved], [data-empty-verified]');
        if (empty) {
            empty.remove();
        }
        zone.prepend(card);
        setCardStatus(card, column);
        updateCounts();
    }

    function postStatus(card, column) {
        var materialId = card.getAttribute('data-material-id');
        if (!materialId || !reviewUrl || !COLUMN_META[column]) {
            return;
        }
        var body = new URLSearchParams();
        body.set('action', 'set_status');
        body.set('status', column);
        body.set('material_id', materialId);
        card.classList.add('is-busy');
        fetch(reviewUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
                'X-CSRFToken': csrf,
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: body.toString(),
            credentials: 'same-origin',
        }).then(function (response) {
            if (!response.ok) {
                throw new Error('bad status');
            }
            return response.json();
        }).then(function (payload) {
            if (!payload || !payload.ok || !payload.status) {
                throw new Error('payload');
            }
            moveCard(card, payload.status);
        }).catch(function () {
            window.alert('Не удалось обновить статус. Обновите страницу и попробуйте снова.');
        }).finally(function () {
            card.classList.remove('is-busy');
        });
    }

    board.addEventListener('dragstart', function (event) {
        var card = event.target.closest('.import-review-card');
        if (!card || !board.contains(card)) {
            return;
        }
        dragCard = card;
        card.classList.add('is-dragging');
        board.classList.add('is-dragging');
        if (event.dataTransfer) {
            event.dataTransfer.effectAllowed = 'move';
            event.dataTransfer.setData('text/plain', card.getAttribute('data-material-id') || '');
        }
    });

    board.addEventListener('dragend', function () {
        if (dragCard) {
            dragCard.classList.remove('is-dragging');
        }
        board.classList.remove('is-dragging');
        setActiveZone(null);
        dragCard = null;
    });

    board.addEventListener('dragover', function (event) {
        if (!dragCard) {
            return;
        }
        var zone = zoneFromEvent(event);
        if (!zone) {
            setActiveZone(null);
            return;
        }
        event.preventDefault();
        if (event.dataTransfer) {
            event.dataTransfer.dropEffect = 'move';
        }
        setActiveZone(zone);
    });

    board.addEventListener('dragleave', function (event) {
        if (!dragCard) {
            return;
        }
        var related = event.relatedTarget;
        if (related && board.contains(related)) {
            return;
        }
        setActiveZone(null);
    });

    board.addEventListener('drop', function (event) {
        if (!dragCard) {
            return;
        }
        var zone = zoneFromEvent(event);
        event.preventDefault();
        setActiveZone(null);
        if (!zone) {
            return;
        }
        var wantStatus = zone.getAttribute('data-drop-zone') || '';
        var current = dragCard.getAttribute('data-status') || '';
        if (!COLUMN_META[wantStatus] || wantStatus === current) {
            return;
        }
        postStatus(dragCard, wantStatus);
    });
})();
