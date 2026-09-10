/**
 * Manual attendance — the desk marking a student by hand.
 *
 * Three screens post the same four fields to the same endpoint (the group
 * grid, the session roster and the student page). One client keeps the
 * request shape, the CSRF header, the session-expired redirect and the
 * error wording identical on all of them.
 *
 * Usage:
 *   ManualAttendance.mark({groupId, studentId, date, status})  -> Promise<json>
 *   ManualAttendance.addSession({groupId, date})               -> Promise<json>
 *
 * The endpoint URL is read from <body data-manual-attendance-url>, which
 * base.html stamps, so callers never hard-code it.
 */
(function (window, document) {
    'use strict';

    var STATUS_LABELS = {
        present: 'حاضر',
        late: 'متأخر',
        absent: 'غائب',
        exception: 'عذر',
        clear: 'مسح السجل'
    };

    function csrfToken() {
        var input = document.querySelector('[name=csrfmiddlewaretoken]');
        if (input && input.value) { return input.value; }
        var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function endpoint() {
        return (document.body && document.body.dataset.manualAttendanceUrl) || '/attendance/api/manual/';
    }

    function post(payload) {
        return fetch(endpoint(), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin',
            body: JSON.stringify(payload)
        }).then(function (response) {
            if (response.status === 401 || response.redirected) {
                window.location.href = '/accounts/login/?next=' + encodeURIComponent(window.location.pathname);
                throw new Error('الجلسة منتهية');
            }
            return response.json().catch(function () {
                return {success: false, message: 'خطأ في الخادم'};
            });
        });
    }

    function mark(opts) {
        return post({
            group_id: opts.groupId,
            student_id: opts.studentId,
            date: opts.date || '',
            status: opts.status || 'present'
        });
    }

    function addSession(opts) {
        return post({group_id: opts.groupId, date: opts.date || ''});
    }

    window.ManualAttendance = {
        mark: mark,
        addSession: addSession,
        STATUS_LABELS: STATUS_LABELS
    };
})(window, document);
