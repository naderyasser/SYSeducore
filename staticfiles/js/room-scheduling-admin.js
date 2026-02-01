/**
 * Room Scheduling Admin JavaScript
 * جافاسكريبت للفحص الفوري للتعارضات في لوحة الإدارة
 * 
 * This script provides real-time conflict checking for room scheduling
 * in the Django admin interface.
 */

(function ($) {
    'use strict';

    // Cache DOM elements
    var roomField, dayField, timeField, durationField;
    var conflictAlert, availableRoomsList;
    var checkTimeout;

    /**
     * Initialize the conflict checking system
     */
    function initConflictChecker() {
        // Get form fields
        roomField = $('#id_room');
        dayField = $('#id_schedule_day');
        timeField = $('#id_schedule_time');
        durationField = $('#id_session_duration');

        // If we're on the group form page
        if (roomField.length && dayField.length && timeField.length) {
            // Create conflict alert container
            createConflictAlert();

            // Create available rooms list
            createAvailableRoomsList();

            // Bind change events
            roomField.on('change', checkConflict);
            dayField.on('change', checkConflict);
            timeField.on('change', checkConflict);
            durationField.on('change', checkConflict);

            // Initial check
            setTimeout(checkConflict, 500);
        }
    }

    /**
     * Create conflict alert container
     */
    function createConflictAlert() {
        var alertHtml = `
            <div id="conflict-alert" class="conflict-alert" style="display: none;">
                <div class="alert-icon">⛔</div>
                <div class="alert-content">
                    <h4>تعارض في الجدول</h4>
                    <p id="conflict-message"></p>
                    <div id="conflict-details"></div>
                </div>
            </div>
        `;

        // Insert after the session_duration field
        durationField.parent().parent().after(alertHtml);

        conflictAlert = $('#conflict-alert');
    }

    /**
     * Create available rooms list container
     */
    function createAvailableRoomsList() {
        var listHtml = `
            <div id="available-rooms" class="available-rooms" style="display: none;">
                <h4>🏫 القاعات المتاحة في هذا الوقت</h4>
                <div id="rooms-list"></div>
            </div>
        `;

        // Insert after conflict alert
        conflictAlert.after(listHtml);

        availableRoomsList = $('#available-rooms');
    }

    /**
     * Check for conflicts via AJAX
     */
    function checkConflict() {
        var roomId = roomField.val();
        var day = dayField.val();
        var time = timeField.val();
        var duration = durationField.val() || 120;

        // Clear previous timeout
        if (checkTimeout) {
            clearTimeout(checkTimeout);
        }

        // Wait 300ms before checking (debounce)
        checkTimeout = setTimeout(function () {
            if (!roomId || !day || !time) {
                hideConflictAlert();
                hideAvailableRooms();
                return;
            }

            // Show loading state
            showLoading();

            // Make AJAX request
            $.ajax({
                url: '/api/teachers/check-conflict/',
                type: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({
                    room_id: roomId,
                    day: day,
                    time: time,
                    duration: duration,
                    exclude_group_id: getGroupId()
                }),
                headers: {
                    'X-CSRFToken': getCsrfToken()
                },
                success: function (response) {
                    hideLoading();

                    if (response.has_conflict) {
                        showConflictAlert(response.conflict);
                        loadAvailableRooms(day, time, duration);
                    } else {
                        hideConflictAlert();
                        showSuccessMessage();
                        loadAvailableRooms(day, time, duration);
                    }
                },
                error: function (xhr) {
                    hideLoading();
                    console.error('Error checking conflict:', xhr);
                }
            });
        }, 300);
    }

    /**
     * Get current group ID (for edit mode)
     */
    function getGroupId() {
        var urlParts = window.location.pathname.split('/');
        if (urlParts[3] === 'change') {
            return urlParts[2];
        }
        return null;
    }

    /**
     * Get CSRF token
     */
    function getCsrfToken() {
        return $('input[name="csrfmiddlewaretoken"]').val() ||
            $('meta[name="csrf-token"]').attr('content') ||
            getCookie('csrftoken');
    }

    /**
     * Get cookie value
     */
    function getCookie(name) {
        var cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            var cookies = document.cookie.split(';');
            for (var i = 0; i < cookies.length; i++) {
                var cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    /**
     * Show conflict alert
     */
    function showConflictAlert(conflict) {
        conflictAlert.show();
        conflictAlert.removeClass('alert-success').addClass('alert-error');

        $('#conflict-message').html(conflict.message_ar);
        $('#conflict-details').html(
            '<strong>المجموعة المتعارضة:</strong> ' + conflict.group_name + '<br>' +
            '<strong>الوقت:</strong> ' + conflict.conflict_start + ' - ' + conflict.conflict_end
        );

        // Highlight conflicting fields
        roomField.addClass('conflict-field');
        dayField.addClass('conflict-field');
        timeField.addClass('conflict-field');
    }

    /**
     * Hide conflict alert
     */
    function hideConflictAlert() {
        conflictAlert.hide();

        // Remove highlight
        roomField.removeClass('conflict-field');
        dayField.removeClass('conflict-field');
        timeField.removeClass('conflict-field');
    }

    /**
     * Show success message
     */
    function showSuccessMessage() {
        var successHtml = `
            <div class="success-message" style="color: green; padding: 10px; background: #d4edda; border-radius: 4px; margin-top: 10px;">
                ✅ القاعة متاحة في هذا الوقت
            </div>
        `;

        // Remove existing success message
        $('.success-message').remove();

        // Add new success message
        durationField.parent().parent().after(successHtml);

        // Auto-hide after 3 seconds
        setTimeout(function () {
            $('.success-message').fadeOut();
        }, 3000);
    }

    /**
     * Load available rooms
     */
    function loadAvailableRooms(day, time, duration) {
        $.ajax({
            url: '/api/teachers/rooms/available/',
            type: 'GET',
            data: {
                day: day,
                time: time,
                duration: duration
            },
            success: function (response) {
                displayAvailableRooms(response.rooms);
            },
            error: function (xhr) {
                console.error('Error loading available rooms:', xhr);
            }
        });
    }

    /**
     * Display available rooms
     */
    function displayAvailableRooms(rooms) {
        var html = '<div class="rooms-grid">';

        rooms.forEach(function (room) {
            var statusClass = room.is_available ? 'available' : 'unavailable';
            var statusIcon = room.is_available ? '✅' : '🔒';

            html += `
                <div class="room-card ${statusClass}">
                    <div class="room-icon">${statusIcon}</div>
                    <div class="room-info">
                        <strong>${room.name}</strong><br>
                        <small>السعة: ${room.capacity} طالب</small>
                    </div>
                </div>
            `;
        });

        html += '</div>';

        $('#rooms-list').html(html);
        availableRoomsList.show();
    }

    /**
     * Hide available rooms
     */
    function hideAvailableRooms() {
        availableRoomsList.hide();
    }

    /**
     * Show loading state
     */
    function showLoading() {
        var loadingHtml = `
            <div class="loading-indicator" style="text-align: center; padding: 10px;">
                <span style="color: #007bff;">جاري الفحص...</span>
            </div>
        `;

        // Remove existing loading
        $('.loading-indicator').remove();

        // Add loading indicator
        durationField.parent().parent().after(loadingHtml);
    }

    /**
     * Hide loading state
     */
    function hideLoading() {
        $('.loading-indicator').remove();
    }

    /**
     * Prevent form submission if there's a conflict
     */
    function preventSubmitOnConflict() {
        var form = $('form');

        form.on('submit', function (e) {
            if (conflictAlert.is(':visible')) {
                e.preventDefault();
                alert('⛔ يوجد تعارض في الجدول! يرجى حل التعارض قبل الحفظ أو اختيار قاعة أخرى.');
                return false;
            }
        });
    }

    /**
     * Initialize on document ready
     */
    $(document).ready(function () {
        initConflictChecker();
        preventSubmitOnConflict();

        // Also initialize when Django's inline forms are added
        $(document).on('formset:added', function () {
            initConflictChecker();
        });
    });

})(django.jQuery);
