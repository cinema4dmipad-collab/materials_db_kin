(function () {
    'use strict';

    var overlay = document.getElementById('import-busy');
    if (!overlay) {
        return;
    }

    var titleEl = overlay.querySelector('.import-busy__title');
    var metaEl = overlay.querySelector('.import-busy__meta');
    var busy = false;

    var ACTION_MESSAGES = {
        upload: {
            title: 'Загрузка файла',
            meta: 'Читаем файл и готовим мастер импорта…',
        },
        configure: {
            title: 'Настройка листа',
            meta: 'Применяем параметры и открываем колонки…',
        },
        map_preview: {
            title: 'Сборка черновика',
            meta: 'Сопоставляем колонки и проверяем данные…',
        },
        map_iterate: {
            title: 'Построчный режим',
            meta: 'Готовим первую строку…',
        },
        review_apply: {
            title: 'Импорт материалов',
            meta: 'Записываем данные в базу. Не закрывайте страницу…',
        },
        review_iterate_start: {
            title: 'Построчный режим',
            meta: 'Готовим первую строку…',
        },
        iterate_apply: {
            title: 'Запись строки',
            meta: 'Сохраняем текущую строку в базу…',
        },
        iterate_skip: {
            title: 'Пропуск строки',
            meta: 'Переходим к следующей…',
        },
        load_profile: {
            title: 'Загрузка профиля',
            meta: 'Применяем сохранённый маппинг…',
        },
        save_profile: {
            title: 'Сохранение профиля',
            meta: 'Сохраняем маппинг…',
        },
        undo_last_import: {
            title: 'Откат импорта',
            meta: 'Удаляем результат последнего импорта…',
        },
    };

    function showBusy(action) {
        if (busy) {
            return;
        }
        busy = true;
        var message = ACTION_MESSAGES[action] || {
            title: 'Обработка импорта',
            meta: 'Подождите, выполняется запрос…',
        };
        if (titleEl) {
            titleEl.textContent = message.title;
        }
        if (metaEl) {
            metaEl.textContent = message.meta;
        }
        overlay.hidden = false;
        overlay.classList.add('is-active');
        overlay.setAttribute('aria-busy', 'true');
        document.body.classList.add('import-busy-lock');
        // Блокируем UI после текущего тика — иначе disabled submit-кнопка
        // не попадёт в тело POST (браузер собирает поля после обработчиков submit).
        window.setTimeout(function () {
            document.querySelectorAll('button, input[type="submit"], a.btn').forEach(function (el) {
                if (el.tagName === 'A') {
                    el.classList.add('disabled');
                    el.setAttribute('aria-disabled', 'true');
                    return;
                }
                el.disabled = true;
            });
        }, 0);
        document.addEventListener(
            'click',
            function (event) {
                if (!busy) {
                    return;
                }
                event.preventDefault();
                event.stopPropagation();
            },
            true
        );
    }

    function resolveAction(form, submitter) {
        if (submitter && submitter.name === 'action' && submitter.value) {
            return submitter.value;
        }
        var actionInput = form.querySelector('input[name="action"]');
        return actionInput && actionInput.value ? actionInput.value : 'map_preview';
    }

    /**
     * Пока submit ещё не собрал FormData, disabled-кнопки выпадают из POST.
     * Сохраняем name/value нажатой кнопки в hidden, затем блокируем UI.
     */
    function preserveSubmitter(form, submitter) {
        if (!submitter || !submitter.name) {
            return;
        }
        var existing = form.querySelector(
            'input[type="hidden"][data-import-submitter="1"][name="' + submitter.name + '"]'
        );
        if (!existing) {
            existing = document.createElement('input');
            existing.type = 'hidden';
            existing.name = submitter.name;
            existing.setAttribute('data-import-submitter', '1');
            form.appendChild(existing);
        }
        existing.value = submitter.value || '';
    }

    /**
     * Пока детали черновика свёрнуты, не шлём сотни include_* —
     * сервер оставит флаги из сессии. Иначе легко упереться в лимит полей POST.
     */
    function trimReviewIncludes(form) {
        if (!form.querySelector('input[name="review_marker"]')) {
            return;
        }
        var details = document.getElementById('import-draft-details');
        var expanded = details && details.classList.contains('show');
        if (expanded) {
            return;
        }
        form.querySelectorAll('input[name^="include_"]').forEach(function (el) {
            el.disabled = true;
        });
    }

    function hideBusy() {
        busy = false;
        overlay.hidden = true;
        overlay.classList.remove('is-active');
        overlay.setAttribute('aria-busy', 'false');
        document.body.classList.remove('import-busy-lock');
    }

    document.querySelectorAll('form').forEach(function (form) {
        form.addEventListener('submit', function (event) {
            if (form.getAttribute('data-import-busy') === '0') {
                return;
            }
            // confirm() на откате: если пользователь отменил — не показываем оверлей
            if (event.defaultPrevented) {
                return;
            }
            var submitter = event.submitter || null;
            if (submitter && submitter.getAttribute('data-import-busy') === '0') {
                return;
            }
            trimReviewIncludes(form);
            preserveSubmitter(form, submitter);
            showBusy(resolveAction(form, submitter));
        });
    });

    // Если запрос оборвался / bfcache — не оставляем вечный оверлей
    window.addEventListener('pageshow', function (event) {
        if (event.persisted) {
            hideBusy();
        }
    });
    window.addEventListener('pagehide', function () {
        // навигация началась — оверлей снимется с новой страницей;
        // на обрыве pageshow/visibility почистит
    });
})();
