/**
 * The browser-side twin of ``apps.core.templatetags.money_format``.
 *
 * Several screens render an amount from the server and then overwrite it from
 * an API response — the settlement sheet rewrites its four totals and two
 * columns after every edit. When the server said "1,570.50 ج.م" and the script
 * wrote back the raw "1570.50", the same figure changed shape the moment you
 * touched the page. Both sides go through the same rules now: round to
 * piastres, drop a zero fraction, group thousands, and join the currency with
 * a non-breaking space so it cannot wrap onto its own line.
 */
(function (window) {
    'use strict';

    var CURRENCY = 'ج.م';
    var NBSP = ' ';

    function money(value, fallback) {
        var number = typeof value === 'number' ? value : parseFloat(value);
        if (value === null || value === undefined || value === '' ||
            !isFinite(number)) {
            return fallback === undefined ? '0' : fallback;
        }
        // Round to piastres first so 1250.567 groups as 1,250.57 rather than
        // being handed to the formatter at full precision.
        var rounded = Math.round(number * 100) / 100;
        var whole = Math.abs(rounded % 1) < 1e-9;
        return rounded.toLocaleString('en-US', {
            minimumFractionDigits: whole ? 0 : 2,
            maximumFractionDigits: 2
        });
    }

    function formatEgp(value, fallback) {
        return money(value, fallback) + NBSP + CURRENCY;
    }

    window.formatMoney = money;
    window.formatEgp = formatEgp;
})(window);
