/**
 * Cycle B-XZ / B-YZ / C-scan thumbnails under scan tiles and on the detail card.
 * Empty kinds (no file) are skipped so arrows only move between real images.
 */
(function () {
    'use strict';

    function slidesOf(root) {
        return Array.prototype.slice.call(
            root.querySelectorAll('[data-scan-preview-slide]')
        );
    }

    function slidesWithImage(slides) {
        return slides.filter(function (slide) {
            return slide.getAttribute('data-has-image') === '1';
        });
    }

    function setIndex(root, index) {
        var slides = slidesOf(root);
        if (!slides.length) {
            return;
        }
        var images = slidesWithImage(slides);
        var cycle = images.length ? images : slides;
        var n = cycle.length;
        index = ((index % n) + n) % n;
        root.dataset.scanPreviewIndex = String(index);
        var activeSlide = cycle[index];
        slides.forEach(function (slide) {
            var active = slide === activeSlide;
            slide.classList.toggle('is-active', active);
            slide.hidden = !active;
        });
        var label = activeSlide.getAttribute('data-scan-preview-label') || '';
        root.querySelectorAll('[data-scan-preview-caption]').forEach(function (el) {
            el.textContent = label;
        });
        var nav = root.querySelector('.scan-preview-carousel__nav');
        if (nav) {
            nav.hidden = images.length < 2;
        }
    }

    function initialIndex(root, slides) {
        var preferred = root.getAttribute('data-initial-kind') || 'c';
        var images = slidesWithImage(slides);
        var cycle = images.length ? images : slides;
        var preferredIndex = 0;
        cycle.forEach(function (slide, i) {
            if (slide.getAttribute('data-kind') === preferred) {
                preferredIndex = i;
            }
        });
        var preferredSlide = cycle[preferredIndex];
        if (preferredSlide && preferredSlide.getAttribute('data-has-image') === '1') {
            return preferredIndex;
        }
        return 0;
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
