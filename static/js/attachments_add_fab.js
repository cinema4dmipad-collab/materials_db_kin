(function () {
    'use strict';

    function init() {
        var anchor = document.querySelector('[data-attachments-add-anchor]');
        var fab = document.querySelector('[data-attachments-add-fab]');
        if (!anchor || !fab || !('IntersectionObserver' in window)) {
            return;
        }

        var observer = new IntersectionObserver(
            function (entries) {
                entries.forEach(function (entry) {
                    fab.classList.toggle('is-visible', !entry.isIntersecting);
                    fab.setAttribute('aria-hidden', entry.isIntersecting ? 'true' : 'false');
                    if (entry.isIntersecting) {
                        fab.setAttribute('tabindex', '-1');
                    } else {
                        fab.removeAttribute('tabindex');
                    }
                });
            },
            {
                root: null,
                // Trigger a bit before the header button fully leaves the top.
                rootMargin: '-12px 0px 0px 0px',
                threshold: 0,
            }
        );
        observer.observe(anchor);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
