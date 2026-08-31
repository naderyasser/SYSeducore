/**
 * Live search for the teachers / groups directory screens.
 *
 * Progressive enhancement over a plain <form method="get">: with JS off, the
 * form still submits and the server renders the same filtered, unpaginated
 * list. With JS on, typing fetches `?q=…&partial=1` and swaps the table body.
 *
 * Why the server does the filtering rather than hiding rows client-side: the
 * list is paginated, so the rows in the DOM are only the first page. Filtering
 * what is already loaded would search 25 of 300 teachers and confidently
 * report "no results" for the other 275. The server-side search deliberately
 * bypasses pagination (see `_search_results` in apps/teachers/views.py) so a
 * search really does return every match.
 */
(function (window, document) {
    'use strict';

    var DEBOUNCE_MS = 250;

    function init(form) {
        var input = form.querySelector('input[name="q"]');
        var clearBtn = form.querySelector('.directory-search-clear');
        var results = document.querySelector(form.dataset.results || '#directory-results');
        var meta = document.querySelector(form.dataset.meta || '#directory-meta');
        if (!input || !results) return;

        var tbody = results.tagName === 'TBODY' ? results : results.querySelector('tbody');
        if (!tbody) return;

        var timer = null;
        var inFlight = null;
        var lastRendered = input.value;

        function url(term) {
            var base = form.getAttribute('action') || window.location.pathname;
            var params = new URLSearchParams();
            if (term) params.set('q', term);
            params.set('partial', '1');
            return base + '?' + params.toString();
        }

        function pushHistory(term) {
            // replaceState, not pushState: every keystroke would otherwise add
            // a history entry and the back button would replay the typing.
            var params = new URLSearchParams(window.location.search);
            if (term) params.set('q', term); else params.delete('q');
            params.delete('partial');
            params.delete('page');
            var qs = params.toString();
            window.history.replaceState(
                {}, '', window.location.pathname + (qs ? '?' + qs : '')
            );
        }

        function run(term) {
            if (term === lastRendered) return;
            // A newer keystroke wins: without this, a slow response for "أح"
            // can land after "أحمد" and overwrite the newer, correct rows.
            if (inFlight) inFlight.abort();
            var controller = new AbortController();
            inFlight = controller;
            results.classList.add('is-loading');

            fetch(url(term), {
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin',
                signal: controller.signal
            })
                .then(function (response) {
                    if (response.status === 401 || response.redirected) {
                        // Session expired mid-search: a silent failure here
                        // looks like "the search is broken".
                        window.location.href = '/accounts/login/';
                        throw new Error('session');
                    }
                    if (!response.ok) throw new Error('http ' + response.status);
                    return response.text();
                })
                .then(function (html) {
                    var doc = new DOMParser().parseFromString(html, 'text/html');
                    var rows = doc.querySelector('[data-part="rows"]');
                    var newMeta = doc.querySelector('[data-part="meta"]');
                    if (rows) tbody.innerHTML = rows.innerHTML;
                    if (meta && newMeta) meta.innerHTML = newMeta.innerHTML;
                    lastRendered = term;
                    pushHistory(term);
                    // Searching bypasses pagination, so any pager on screen is
                    // now describing a list that is no longer there.
                    document.querySelectorAll('[data-directory-pagination]').forEach(
                        function (nav) { nav.hidden = Boolean(term); }
                    );
                })
                .catch(function (error) {
                    if (error.name === 'AbortError' || error.message === 'session') return;
                    // Fall back to a real navigation rather than leaving the
                    // user staring at stale rows.
                    form.submit();
                })
                .then(function () {
                    if (inFlight === controller) {
                        inFlight = null;
                        results.classList.remove('is-loading');
                    }
                });
        }

        function schedule() {
            var term = input.value.trim();
            if (clearBtn) clearBtn.hidden = !term;
            window.clearTimeout(timer);
            timer = window.setTimeout(function () { run(term); }, DEBOUNCE_MS);
        }

        input.addEventListener('input', schedule);
        input.addEventListener('search', schedule);  // native clear (×) on type=search

        form.addEventListener('submit', function (event) {
            // Enter should not reload the page when the rows are already live.
            event.preventDefault();
            window.clearTimeout(timer);
            run(input.value.trim());
        });

        if (clearBtn) {
            clearBtn.addEventListener('click', function () {
                input.value = '';
                clearBtn.hidden = true;
                input.focus();
                window.clearTimeout(timer);
                run('');
            });
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.directory-search-form').forEach(init);
    });
})(window, document);
