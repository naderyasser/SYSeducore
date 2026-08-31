/**
 * Stage → academic-year linkage for every "المرحلة الدراسية / السنة الدراسية"
 * pair in the system.
 *
 * The bug this replaces: the old code kept all six years in the DOM and hid
 * the ones that did not apply with `option.style.display = 'none'`. Styling an
 * <option> is not something browsers are obliged to honour, and Safari/iOS in
 * particular ignores it — so "إعدادي" kept offering six years there while
 * looking correct in Chrome. Disabling the option is honoured, but the entry
 * still sits in the list, greyed out, which is not what was asked for either.
 *
 * The fix is to rebuild the <select> from the stage map: an option that does
 * not apply is not in the document at all, so no browser can show it.
 *
 * Stages with no academic year (تأسيس / كورسات) hide the year field entirely
 * and post an empty value. `apps.core.education.normalize_stage_year` enforces
 * the same rule server-side, so a stale or hand-crafted POST cannot store a
 * year the stage does not have.
 */
(function (window, document) {
    'use strict';

    function readMap() {
        var el = document.getElementById('education-stage-years');
        if (!el) return {};
        try {
            return JSON.parse(el.textContent || '{}');
        } catch (err) {
            return {};
        }
    }

    var STAGE_YEARS = readMap();

    /**
     * Years available for a stage, as [{value, label}].
     *
     * An empty/unknown stage returns every year: "no stage chosen" on a filter
     * must not hide rows, and a legacy record whose stage predates the current
     * table has to stay editable. Mirrors `education.years_for_stage`.
     */
    function yearsFor(stage, labelSet) {
        var set = labelSet || 'short';
        if (!stage) {
            var all = [];
            Object.keys(STAGE_YEARS).forEach(function (key) {
                (STAGE_YEARS[key][set] || []).forEach(function (year) {
                    if (!all.some(function (y) { return y.value === year.value; })) {
                        all.push(year);
                    }
                });
            });
            all.sort(function (a, b) { return Number(a.value) - Number(b.value); });
            return all;
        }
        var entry = STAGE_YEARS[stage];
        if (!entry) return [];
        return entry[set] || [];
    }

    function stageHasYears(stage) {
        if (!stage) return true;
        var entry = STAGE_YEARS[stage];
        if (!entry) return true;
        return (entry.short || []).length > 0;
    }

    /**
     * Wire a stage <select> to a year <select>.
     *
     * options:
     *   labelSet   'short' (الأول) or 'grade' (الصف الأول) — matches whichever
     *              model owns the field, so the visible wording does not change.
     *   wrapper    element hidden when the stage has no years; defaults to the
     *              year select's closest column/form-group.
     *   placeholder text of the leading empty option (kept, so "الكل"/"اختر"
     *              filters keep working).
     *
     * Returns a re-apply function; call it after replacing either select.
     */
    function link(stageSelect, yearSelect, options) {
        if (!stageSelect || !yearSelect) return function () {};
        var opts = options || {};
        var labelSet = opts.labelSet || 'short';
        var wrapper = opts.wrapper !== undefined
            ? opts.wrapper
            : yearSelect.closest('.col-md-3, .col-md-4, .col-md-6, .mb-3, .form-group');
        var firstOption = yearSelect.querySelector('option[value=""]');
        var placeholder = opts.placeholder !== undefined
            ? opts.placeholder
            : (firstOption ? firstOption.textContent : '');
        var noYearLabel = opts.noYearLabel || 'لا يوجد';

        // On the very first pass prefer data-selected: the server writes the
        // stored year there, and it survives even if the browser has not
        // applied the `selected` attribute yet when this runs.
        var firstPass = true;

        function apply() {
            var stage = stageSelect.value;
            // Remember the selection so switching away and back does not lose
            // a still-valid year (إعدادي/الثالث → ثانوي keeps "الثالث").
            var previous = firstPass
                ? (yearSelect.dataset.selected || yearSelect.value)
                : yearSelect.value;
            firstPass = false;
            var years = yearsFor(stage, labelSet);
            var hasYears = stageHasYears(stage);

            yearSelect.innerHTML = '';

            if (!hasYears) {
                // تأسيس / كورسات: no academic year exists. Show "لا يوجد",
                // disable the control and post an empty value.
                var none = document.createElement('option');
                none.value = '';
                none.textContent = noYearLabel;
                yearSelect.appendChild(none);
                yearSelect.value = '';
                yearSelect.disabled = true;
                yearSelect.setAttribute('data-no-year', 'true');
                if (wrapper) wrapper.style.display = 'none';
                yearSelect.dispatchEvent(new Event('change', { bubbles: true }));
                return;
            }

            yearSelect.disabled = false;
            yearSelect.removeAttribute('data-no-year');
            if (wrapper) wrapper.style.display = '';

            var blank = document.createElement('option');
            blank.value = '';
            blank.textContent = placeholder;
            yearSelect.appendChild(blank);

            years.forEach(function (year) {
                var opt = document.createElement('option');
                opt.value = year.value;
                opt.textContent = year.label;
                yearSelect.appendChild(opt);
            });

            // Only restore a year the new stage actually has; otherwise fall
            // back to blank rather than silently keeping an impossible pair.
            yearSelect.value = years.some(function (y) { return y.value === previous; })
                ? previous
                : '';
            yearSelect.dispatchEvent(new Event('change', { bubbles: true }));
        }

        stageSelect.addEventListener('change', apply);
        apply();
        return apply;
    }

    window.EducationStageYear = {
        map: STAGE_YEARS,
        yearsFor: yearsFor,
        stageHasYears: stageHasYears,
        link: link
    };
})(window, document);
