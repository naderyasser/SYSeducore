/**
 * Searchable dropdown (combobox) — type to filter a long <select>.
 *
 * Written against the DOM directly rather than pulling in Select2: Select2
 * needs jQuery, and this project ships no jQuery at all, so that one control
 * would have cost two extra CDN dependencies on every page. This is the same
 * interaction in ~150 lines with no dependency and correct RTL behaviour.
 *
 * Progressive enhancement: the original <select> stays in the DOM (hidden) and
 * remains the thing that submits, so the server contract is unchanged and a
 * page whose JS fails to load still shows a working native dropdown.
 *
 * Usage:
 *   SearchableSelect.enhance(document.getElementById('filter_teacher'), {
 *       placeholder: 'ابحث عن مدرس...'
 *   });
 *   SearchableSelect.enhanceAll();   // every [data-searchable] select
 *
 * Changing the underlying select from code still works — fire a 'change'
 * event on it and the widget re-reads its options and label.
 */
(function (window, document) {
    'use strict';

    var idCounter = 0;

    function normalize(text) {
        // Arabic typing is inconsistent about hamza forms and ta-marbuta, and
        // a receptionist searching "احمد" must find "أحمد". Diacritics and the
        // tatweel elongation are stripped for the same reason.
        return (text || '')
            .toString()
            .trim()
            .toLowerCase()
            .replace(/[ً-ْـ]/g, '')
            .replace(/[أإآٱ]/g, 'ا')
            .replace(/ى/g, 'ي')
            .replace(/ة/g, 'ه')
            .replace(/\s+/g, ' ');
    }

    function enhance(select, options) {
        if (!select || select.dataset.searchableReady === 'true') return null;
        var opts = options || {};
        var placeholder = opts.placeholder || select.getAttribute('data-placeholder') || 'ابحث...';
        var emptyText = opts.emptyText || 'لا توجد نتائج';

        idCounter += 1;
        var listId = 'searchable-select-list-' + idCounter;

        var wrap = document.createElement('div');
        wrap.className = 'searchable-select';

        var input = document.createElement('input');
        input.type = 'text';
        input.className = select.className.replace(/form-select/g, 'form-control') || 'form-control';
        input.setAttribute('role', 'combobox');
        input.setAttribute('aria-expanded', 'false');
        input.setAttribute('aria-controls', listId);
        input.setAttribute('aria-autocomplete', 'list');
        input.autocomplete = 'off';
        input.placeholder = placeholder;

        var menu = document.createElement('div');
        menu.className = 'searchable-select-menu';
        menu.id = listId;
        menu.setAttribute('role', 'listbox');
        menu.hidden = true;

        select.parentNode.insertBefore(wrap, select);
        wrap.appendChild(input);
        wrap.appendChild(menu);
        wrap.appendChild(select);
        select.classList.add('searchable-select-native');
        select.dataset.searchableReady = 'true';
        // Kept focusable-out of the tab order but still submitted with the form.
        select.tabIndex = -1;
        select.setAttribute('aria-hidden', 'true');

        var activeIndex = -1;
        var visible = [];

        function currentLabel() {
            var opt = select.options[select.selectedIndex];
            return opt ? opt.textContent.trim() : '';
        }

        function syncInput() {
            input.value = currentLabel();
        }

        function close() {
            menu.hidden = true;
            input.setAttribute('aria-expanded', 'false');
            activeIndex = -1;
            syncInput();
        }

        function choose(index) {
            select.selectedIndex = index;
            select.dispatchEvent(new Event('change', { bubbles: true }));
            close();
        }

        function render(term) {
            var needle = normalize(term);
            menu.innerHTML = '';
            visible = [];

            Array.prototype.forEach.call(select.options, function (opt, index) {
                var label = opt.textContent.trim();
                // A blank-valued first option ("-- الكل --") is a real choice —
                // it is how the user clears the filter — so it is matched and
                // listed like any other rather than being filtered out.
                if (needle && normalize(label).indexOf(needle) === -1) return;

                var item = document.createElement('div');
                item.className = 'searchable-select-item';
                item.setAttribute('role', 'option');
                item.textContent = label;
                if (index === select.selectedIndex) {
                    item.classList.add('is-selected');
                    item.setAttribute('aria-selected', 'true');
                }
                // mousedown, not click: blur would close the menu first.
                item.addEventListener('mousedown', function (event) {
                    event.preventDefault();
                    choose(index);
                });
                menu.appendChild(item);
                visible.push({ index: index, el: item });
            });

            if (!visible.length) {
                var empty = document.createElement('div');
                empty.className = 'searchable-select-empty';
                empty.textContent = emptyText;
                menu.appendChild(empty);
            }
            activeIndex = -1;
        }

        function open() {
            render(input.value === currentLabel() ? '' : input.value);
            menu.hidden = false;
            input.setAttribute('aria-expanded', 'true');
        }

        function highlight(delta) {
            if (menu.hidden) { open(); return; }
            if (!visible.length) return;
            activeIndex = (activeIndex + delta + visible.length) % visible.length;
            visible.forEach(function (entry, i) {
                entry.el.classList.toggle('is-active', i === activeIndex);
            });
            visible[activeIndex].el.scrollIntoView({ block: 'nearest' });
        }

        input.addEventListener('focus', function () {
            input.select();
            open();
        });
        input.addEventListener('input', function () {
            render(input.value);
            menu.hidden = false;
            input.setAttribute('aria-expanded', 'true');
        });
        input.addEventListener('keydown', function (event) {
            if (event.key === 'ArrowDown') { event.preventDefault(); highlight(1); }
            else if (event.key === 'ArrowUp') { event.preventDefault(); highlight(-1); }
            else if (event.key === 'Enter') {
                if (!menu.hidden && activeIndex >= 0) {
                    event.preventDefault();
                    choose(visible[activeIndex].index);
                } else if (!menu.hidden && visible.length === 1) {
                    // One match left and the user hits Enter: take it. Saves a
                    // keystroke on the desk's most common action.
                    event.preventDefault();
                    choose(visible[0].index);
                }
            } else if (event.key === 'Escape') { close(); }
        });
        input.addEventListener('blur', function () {
            // Deferred: a mousedown on an item must land before the close.
            window.setTimeout(close, 120);
        });

        // Keep the widget truthful when the select is driven from code.
        select.addEventListener('change', syncInput);

        syncInput();
        return { refresh: syncInput, element: wrap };
    }

    function enhanceAll(root) {
        var scope = root || document;
        Array.prototype.forEach.call(
            scope.querySelectorAll('select[data-searchable]'),
            function (select) { enhance(select); }
        );
    }

    window.SearchableSelect = { enhance: enhance, enhanceAll: enhanceAll };

    document.addEventListener('DOMContentLoaded', function () { enhanceAll(); });
})(window, document);
