(function () {
    'use strict';

    var STORAGE_KEY = 'materials-db:sidebar-collapsed';
    var shell = document.getElementById('appShell');
    var toggle = document.getElementById('appSidebarToggle');
    var backdrop = document.getElementById('appShellBackdrop');
    var mobileQuery = window.matchMedia('(max-width: 991.98px)');

    if (!shell || !toggle) {
        return;
    }

    function isMobile() {
        return mobileQuery.matches;
    }

    function setDesktopCollapsed(collapsed) {
        shell.classList.toggle('app-shell--sidebar-collapsed', collapsed);
        toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        try {
            localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0');
        } catch (e) {
            /* ignore */
        }
    }

    function setMobileOpen(open) {
        shell.classList.toggle('app-shell--sidebar-open', open);
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (backdrop) {
            backdrop.hidden = !open;
        }
    }

    function applyLayout() {
        shell.classList.remove('app-shell--sidebar-collapsed', 'app-shell--sidebar-open');
        if (backdrop) {
            backdrop.hidden = true;
        }
        if (isMobile()) {
            setMobileOpen(false);
            toggle.setAttribute('aria-expanded', 'false');
            return;
        }
        var collapsed = false;
        try {
            collapsed = localStorage.getItem(STORAGE_KEY) === '1';
        } catch (e) {
            collapsed = false;
        }
        setDesktopCollapsed(collapsed);
    }

    toggle.addEventListener('click', function () {
        if (isMobile()) {
            setMobileOpen(!shell.classList.contains('app-shell--sidebar-open'));
            return;
        }
        setDesktopCollapsed(!shell.classList.contains('app-shell--sidebar-collapsed'));
    });

    if (backdrop) {
        backdrop.addEventListener('click', function () {
            setMobileOpen(false);
        });
    }

    if (typeof mobileQuery.addEventListener === 'function') {
        mobileQuery.addEventListener('change', applyLayout);
    } else if (typeof mobileQuery.addListener === 'function') {
        mobileQuery.addListener(applyLayout);
    }
    window.addEventListener('resize', applyLayout);
    applyLayout();
})();
