/**
 * Cycle B-XZ / B-YZ / C-scan thumbnails under scan tiles and on the detail card.
 */
(function () {
    'use strict';

    function slidesOf(root) {
        return Array.prototype.slice.call(
            root.querySelectorAll('[data-scan-preview-slide]')
        );
    }

    function setIndex(root, index) {
        var slides = slidesOf(root);
        if (!slides.length) {
            return;
        }
        var n = slides.length;
        index = ((index % n) + n) % n;
        root.dataset.scanPreviewIndex = String(index);
        slides.forEach(function (slide, i) {
            var active = i === index;
            slide.classList.toggle('is-active', active);
            slide.hidden = !active;
        });
        var label = slides[index].getAttribute('data-scan-preview-label') || '';
        root.querySelectorAll('[data-scan-preview-caption]').forEach(function (el) {
            el.textContent = label;
        });
    }

    function initialIndex(root, slides) {
        var preferred = root.getAttribute('data-initial-kind') || 'c';
        var withImage = -1;
        var preferredIndex = 0;
        slides.forEach(function (slide, i) {
            if (slide.getAttribute('data-kind') === preferred) {
                preferredIndex = i;
            }
            if (withImage < 0 && slide.getAttribute('data-has-image') === '1') {
                withImage = i;
            }
        });
        var preferredSlide = slides[preferredIndex];
        if (preferredSlide && preferredSlide.getAttribute('data-has-image') === '1') {
            return preferredIndex;
        }
        return withImage >= 0 ? withImage : preferredIndex;
    }

    function init(root) {
        if (root.dataset.scanPreviewReady === '1') {
            return;
        }
        root.dataset.scanPreviewReady = '1';
        setIndex(root, initialIndex(root, slidesOf(root)));
    }

    function initAll() {
        document.querySelectorAll('[data-scan-preview-carousel]').forEach(init);
    }

    document.addEventListener('click', function (event) {
        var btn = event.target.closest('[data-scan-preview-dir]');
        if (!btn) {
            return;
        }
        var root = btn.closest('[data-scan-preview-carousel]');
        if (!root) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        var dir = parseInt(btn.getAttribute('data-scan-preview-dir'), 10) || 0;
        var current = parseInt(root.dataset.scanPreviewIndex || '0', 10) || 0;
        setIndex(root, current + dir);
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }
})();
