(function () {
    'use strict';

    var PAD = 8;
    var GAP = 8;
    var active = null;
    var pinned = false;

    function tipFromTrigger(trigger) {
        if (trigger._importHelpTip && document.body.contains(trigger._importHelpTip)) {
            return trigger._importHelpTip;
        }
        var child = null;
        for (var i = 0; i < trigger.children.length; i += 1) {
            if (trigger.children[i].classList.contains('import-help__tip')) {
                child = trigger.children[i];
                break;
            }
        }
        if (child) {
            trigger._importHelpTip = child;
        }
        return child;
    }

    function rememberHome(tip, parent, next) {
        if (!tip._importHelpHomeParent) {
            tip._importHelpHomeParent = parent;
            tip._importHelpHomeNext = next;
        }
    }

    function restoreTip(entry) {
        if (!entry || !entry.tip) return;
        var tip = entry.tip;
        tip.classList.remove('is-open', 'is-below');
        tip.style.top = '';
        tip.style.left = '';
        tip.style.right = '';
        tip.style.bottom = '';
        tip.style.transform = '';
        var homeParent = tip._importHelpHomeParent;
        var homeNext = tip._importHelpHomeNext;
        if (homeParent && document.body.contains(homeParent)) {
            if (homeNext && homeNext.parentNode === homeParent) {
                homeParent.insertBefore(tip, homeNext);
            } else {
                homeParent.appendChild(tip);
            }
        }
    }

    function hideActive() {
        if (!active) return;
        if (active.tip) {
            active.tip.classList.remove('is-pinned');
        }
        restoreTip(active);
        active = null;
        pinned = false;
    }

    function placeTip(trigger, tip) {
        rememberHome(tip, tip.parentNode, tip.nextSibling);
        if (tip.parentNode !== document.body) {
            document.body.appendChild(tip);
        }
        tip.classList.add('is-open');
        tip.classList.remove('is-below');
        tip.style.top = '0px';
        tip.style.left = '0px';
        tip.style.right = 'auto';
        tip.style.bottom = 'auto';
        tip.style.transform = 'none';

        var tr = trigger.getBoundingClientRect();
        var tipR = tip.getBoundingClientRect();
        var top = tr.top - tipR.height - GAP;
        var below = false;
        if (top < PAD) {
            top = tr.bottom + GAP;
            below = true;
        }
        if (top + tipR.height > window.innerHeight - PAD) {
            top = Math.max(PAD, window.innerHeight - tipR.height - PAD);
        }
        var left = tr.left + tr.width / 2 - tipR.width / 2;
        var maxLeft = Math.max(PAD, window.innerWidth - tipR.width - PAD);
        left = Math.min(Math.max(PAD, left), maxLeft);

        tip.style.top = Math.round(top) + 'px';
        tip.style.left = Math.round(left) + 'px';
        tip.classList.toggle('is-below', below);

        return { trigger: trigger, tip: tip };
    }

    function showFor(trigger) {
        var tip = tipFromTrigger(trigger);
        if (!tip) return;
        if (active && active.trigger !== trigger) {
            hideActive();
        }
        active = placeTip(trigger, tip);
        tip.classList.toggle('is-pinned', pinned);
    }

    document.addEventListener('pointerover', function (event) {
        var trigger = event.target.closest && event.target.closest('.import-help__trigger');
        if (!trigger || !document.body.contains(trigger)) return;
        showFor(trigger);
    });

    document.addEventListener('pointerout', function (event) {
        if (!active || pinned) return;
        var fromTrigger = event.target.closest && event.target.closest('.import-help__trigger');
        if (fromTrigger !== active.trigger) return;
        var related = event.relatedTarget;
        var toTrigger = related && related.closest && related.closest('.import-help__trigger');
        if (toTrigger === active.trigger) return;
        hideActive();
    });

    document.addEventListener('focusin', function (event) {
        var trigger = event.target.closest && event.target.closest('.import-help__trigger');
        if (trigger) showFor(trigger);
    });

    document.addEventListener('focusout', function () {
        window.setTimeout(function () {
            if (!active || pinned) return;
            var focused = document.activeElement;
            if (focused && (focused === active.trigger || active.trigger.contains(focused))) return;
            hideActive();
        }, 0);
    });

    document.addEventListener('click', function (event) {
        var trigger = event.target.closest && event.target.closest('.import-help__trigger');
        if (trigger) {
            if (pinned && active && active.trigger === trigger) {
                hideActive();
                return;
            }
            pinned = true;
            showFor(trigger);
            return;
        }
        if (pinned && active && active.tip && active.tip.contains(event.target)) {
            return;
        }
        if (pinned) {
            hideActive();
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            hideActive();
        }
    });

    window.addEventListener('scroll', hideActive, true);
    window.addEventListener('resize', hideActive);
})();
