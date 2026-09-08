/**
 * Global quick search in the top bar: type a teacher, group or student and
 * jump straight to their page.
 *
 * Progressive enhancement over a plain <form method="get"> that submits to
 * the groups directory: with JS off, Enter still finds the term there. With
 * JS on, keystrokes are debounced and fetched from /api/quick-search/, the
 * newest request always wins (AbortController — the pattern from
 * directory-search.js), and the dropdown is keyboard-navigable.
 */
(function (window, document) {
    'use strict';

    var DEBOUNCE_MS = 200;
    var MIN_CHARS = 2;
    var SECTIONS = [
        { key: 'groups',   title: 'المجموعات', icon: 'bi-collection' },
        { key: 'teachers', title: 'المدرسين',  icon: 'bi-person-workspace' },
        { key: 'students', title: 'الطلاب',    icon: 'bi-people' }
    ];

    function esc(text) {
        return String(text == null ? '' : text)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function init(root) {
        var input = root.querySelector('input[type="search"]');
        var menu = root.querySelector('.quick-search-menu');
        var toggle = root.querySelector('.quick-search-toggle');
        if (!input || !menu) return;

        var endpoint = root.dataset.endpoint;
        var timer = null;
        var inFlight = null;
        var active = -1;
        var items = [];

        function open() { root.classList.add('is-open'); menu.hidden = false; }
        function close() { root.classList.remove('is-open'); menu.hidden = true; active = -1; }

        function render(data) {
            items = [];
            var html = '';
            SECTIONS.forEach(function (sec) {
                var block = data[sec.key];
                if (!block || !block.items.length) return;
                html += '<div class="quick-search-section"><i class="bi ' + sec.icon + '"></i> ' + sec.title + '</div>';
                block.items.forEach(function (row) {
                    var i = items.length;
                    items.push(row.url);
                    html += '<a class="quick-search-item' + (row.inactive ? ' is-inactive' : '') +
                            '" href="' + esc(row.url) + '" data-index="' + i + '">' +
                            '<span class="qs-label">' + esc(row.label) + '</span>' +
                            (row.hint ? '<span class="qs-hint">' + esc(row.hint) + '</span>' : '') +
                            '</a>';
                });
                if (block.more && data.more_urls && data.more_urls[sec.key]) {
                    var j = items.length;
                    items.push(data.more_urls[sec.key]);
                    html += '<a class="quick-search-item qs-more" href="' + esc(data.more_urls[sec.key]) +
                            '" data-index="' + j + '">كل نتائج ' + sec.title + '…</a>';
                }
            });
            if (!html) {
                html = '<div class="quick-search-empty">لا توجد نتائج لـ "' + esc(data.q) + '"</div>';
            }
            menu.innerHTML = html;
            active = -1;
            open();
        }

        function run(term) {
            if (inFlight) inFlight.abort();
            if (term.length < MIN_CHARS) { close(); return; }
            var controller = new AbortController();
            inFlight = controller;
            fetch(endpoint + '?q=' + encodeURIComponent(term), {
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin',
                signal: controller.signal
            })
                .then(function (r) {
                    if (r.redirected || r.status === 401) {
                        // Session expired mid-search: a silent empty list
                        // reads as "the search is broken".
                        window.location.href = '/accounts/login/';
                        throw new Error('session');
                    }
                    if (r.status === 429 || r.status === 403) {
                        // Throttled, or a permission gate — the person is
                        // still signed in; navigating away would lose their
                        // page for nothing.
                        throw new Error('throttled');
                    }
                    if (!r.ok) throw new Error('http ' + r.status);
                    return r.json();
                })
                .then(function (data) {
                    if (inFlight === controller) render(data);
                })
                .catch(function (e) {
                    if (e.name === 'AbortError' || e.message === 'session') return;
                    menu.innerHTML = '<div class="quick-search-empty">' +
                        (e.message === 'throttled' ? 'محاولات كثيرة، حاول بعد لحظة' : 'تعذّر البحث الآن') +
                        '</div>';
                    open();
                });
        }

        function highlight(delta) {
            var links = menu.querySelectorAll('.quick-search-item');
            if (!links.length) return;
            active = (active + delta + links.length) % links.length;
            links.forEach(function (el, i) { el.classList.toggle('is-active', i === active); });
            links[active].scrollIntoView({ block: 'nearest' });
        }

        input.addEventListener('input', function () {
            clearTimeout(timer);
            var term = input.value.trim();
            timer = setTimeout(function () { run(term); }, DEBOUNCE_MS);
        });

        input.addEventListener('keydown', function (e) {
            if (menu.hidden) return;
            if (e.key === 'ArrowDown') { e.preventDefault(); highlight(1); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); highlight(-1); }
            else if (e.key === 'Enter' && active >= 0) {
                e.preventDefault(); window.location.href = items[active];
            }
            else if (e.key === 'Escape') { close(); input.blur(); }
        });

        input.addEventListener('focus', function () {
            if (menu.innerHTML && input.value.trim().length >= MIN_CHARS) open();
        });

        document.addEventListener('click', function (e) {
            if (!root.contains(e.target)) {
                close();
                if (toggle && !input.value) root.classList.remove('is-expanded');
            }
        });

        // On a phone the box is an icon until tapped, so the page title keeps
        // its room.
        if (toggle) {
            toggle.addEventListener('click', function () {
                root.classList.add('is-expanded');
                input.focus();
            });
        }
    }

    function boot() {
        var roots = document.querySelectorAll('[data-quick-search]');
        for (var i = 0; i < roots.length; i++) init(roots[i]);
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
    else boot();
})(window, document);
