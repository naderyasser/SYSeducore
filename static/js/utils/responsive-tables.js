/**
 * Turns a wide data table into a stack of cards on a phone.
 *
 * The problem it solves: the directory tables carry eight columns. Under
 * 768px that became a horizontal scroll, and because only the body scrolls,
 * a column slid out from under its own heading — you could reach a number
 * without being able to see which number it was. Cells also inherited a
 * global `white-space: nowrap`, so an Arabic group name could not wrap and
 * simply widened the table further.
 *
 * The fix is pure layout, done in CSS (`components.css`, the
 * `.has-card-labels` block). All this script does is give each <td> the text
 * of its column heading in `data-label`, which the CSS then prints beside the
 * value, and mark the table so the card rules switch on. Doing it here rather
 * than in every template means one place to change and no `data-label` to
 * forget on a new column.
 *
 * Progressive enhancement: with JavaScript off nothing is stamped, the class
 * is never added, and the table stays exactly the scrollable table it is
 * today. Live search replaces <tbody> wholesale, so a MutationObserver
 * re-stamps the new rows.
 */
(function (window, document) {
    'use strict';

    var LABELLED = 'has-card-labels';
    var ACTION_HEADINGS = /إجراء|الإجراءات|أدوات|عمليات|تحكم/;

    function text(node) {
        return (node.textContent || '').replace(/\s+/g, ' ').trim();
    }

    /**
     * Column headings, one per real column.
     *
     * The header row with the most cells wins: a table with a grouped header
     * ("المالية" spanning three) has the leaf row second, and the leaf row is
     * the one whose titles match the body cells.
     */
    function headings(table) {
        var head = table.tHead;
        if (!head || !head.rows.length) return null;

        var best = null;
        for (var i = 0; i < head.rows.length; i++) {
            var cells = head.rows[i].cells;
            if (!best || cells.length > best.length) best = cells;
        }
        if (!best || !best.length) return null;

        var labels = [];
        for (var j = 0; j < best.length; j++) {
            var span = parseInt(best[j].getAttribute('colspan'), 10) || 1;
            var label = text(best[j]);
            while (span--) labels.push(label);
        }
        return labels.some(function (l) { return l !== ''; }) ? labels : null;
    }

    function isActionCell(cell, label) {
        if (ACTION_HEADINGS.test(label)) return true;
        // Some tables head the column with an icon alone, so also treat a
        // cell holding two or more controls and nothing else as actions.
        var controls = cell.querySelectorAll('.btn, button');
        if (controls.length < 2) return false;
        var own = text(cell);
        for (var i = 0; i < controls.length; i++) {
            own = own.replace(text(controls[i]), '');
        }
        return own.trim() === '';
    }

    function stampBody(table, labels, body) {
        for (var r = 0; r < body.rows.length; r++) {
            var cells = body.rows[r].cells;
            var column = 0;
            for (var c = 0; c < cells.length; c++) {
                var cell = cells[c];
                var span = parseInt(cell.getAttribute('colspan'), 10) || 1;
                // A spanning cell — the "no results" row, a totals line — has
                // no single column, so it is left unlabelled and the CSS lets
                // it run the full width of the card.
                if (span === 1 && labels[column]) {
                    cell.setAttribute('data-label', labels[column]);
                    if (isActionCell(cell, labels[column])) {
                        cell.classList.add('table-actions');
                    }
                } else {
                    cell.removeAttribute('data-label');
                }
                column += span;
            }
        }
    }

    function stamp(table) {
        var labels = headings(table);
        if (!labels) return;
        for (var b = 0; b < table.tBodies.length; b++) {
            stampBody(table, labels, table.tBodies[b]);
        }
        table.classList.add(LABELLED);
    }

    function watch(table) {
        if (!window.MutationObserver) return;
        // Live search swaps the whole <tbody> contents; the replacement rows
        // arrive as plain markup with no labels on them.
        var observer = new MutationObserver(function () {
            stamp(table);
        });
        for (var b = 0; b < table.tBodies.length; b++) {
            observer.observe(table.tBodies[b], { childList: true });
        }
    }

    function init(root) {
        // Every data table, not just the Bootstrap-classed ones: the students
        // index, the report grids and the group roster all carry their own
        // class (`students-table`, `data-table`, `comp`) and were the widest
        // tables in the project. `stamp` is a no-op on a table without
        // headings, so a layout table is left alone; `data-no-cards` opts one
        // out explicitly.
        var tables = (root || document).getElementsByTagName('table');
        // A live HTMLCollection, and `stamp` adds a class rather than moving
        // nodes, so a snapshot is not needed — but iterate a copy anyway in
        // case a caller passes a root that is itself being rebuilt.
        var list = Array.prototype.slice.call(tables);
        for (var i = 0; i < list.length; i++) {
            var table = list[i];
            if (table.hasAttribute('data-no-cards')) continue;
            stamp(table);
            watch(table);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { init(); });
    } else {
        init();
    }

    window.responsiveTables = { init: init, stamp: stamp };
})(window, document);
