/**
 * Live Monitor JavaScript
 * جافاسكريبت للشاشة الحية لمراقبة الحضور
 * 
 * Features:
 * - Auto-refresh every 5 seconds
 * - Smooth animations for data updates
 * - Full-screen mode support
 * - Room detail modal
 * - Settings management
 */

class LiveMonitor {
    constructor() {
        this.refreshInterval = 5000; // 5 seconds
        this.autoRefresh = true;
        this.refreshTimer = null;
        this.lastData = null;
        this.settings = {
            refreshInterval: 5,
            showAlerts: true,
            enableSounds: false,
            kioskMode: true
        };

        this.init();
    }

    init() {
        // Load settings from localStorage
        this.loadSettings();

        // Initialize UI
        this.initDateTime();
        this.initEventListeners();

        // Load initial data
        this.loadDashboardData();

        // Start auto-refresh
        if (this.autoRefresh) {
            this.startAutoRefresh();
        }

        // Prevent screen sleep in kiosk mode
        if (this.settings.kioskMode) {
            this.enableKioskMode();
        }
    }

    loadSettings() {
        const saved = localStorage.getItem('monitorSettings');
        if (saved) {
            this.settings = { ...this.settings, ...JSON.parse(saved) };
        }

        // Apply settings
        this.refreshInterval = this.settings.refreshInterval * 1000;
        this.autoRefresh = true;

        // Update settings form
        document.getElementById('refresh-interval').value = this.settings.refreshInterval;
        document.getElementById('show-alerts').checked = this.settings.showAlerts;
        document.getElementById('enable-sounds').checked = this.settings.enableSounds;
        document.getElementById('kiosk-mode').checked = this.settings.kioskMode;
    }

    saveSettings() {
        this.settings.refreshInterval = parseInt(document.getElementById('refresh-interval').value);
        this.settings.showAlerts = document.getElementById('show-alerts').checked;
        this.settings.enableSounds = document.getElementById('enable-sounds').checked;
        this.settings.kioskMode = document.getElementById('kiosk-mode').checked;

        localStorage.setItem('monitorSettings', JSON.stringify(this.settings));

        // Apply new settings
        this.refreshInterval = this.settings.refreshInterval * 1000;

        // Restart auto-refresh with new interval
        this.stopAutoRefresh();
        this.startAutoRefresh();

        // Toggle kiosk mode
        if (this.settings.kioskMode) {
            this.enableKioskMode();
        } else {
            this.disableKioskMode();
        }

        // Show success message
        this.showToast('تم حفظ الإعدادات بنجاح', 'success');
    }

    initDateTime() {
        this.updateDateTime();
        setInterval(() => this.updateDateTime(), 1000);
    }

    updateDateTime() {
        const now = new Date();
        const dateOptions = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
        const timeOptions = { hour: '2-digit', minute: '2-digit', second: '2-digit' };

        const arabicDate = now.toLocaleDateString('ar-EG', dateOptions);
        const timeStr = now.toLocaleTimeString('ar-EG', timeOptions);

        document.getElementById('current-date').textContent = arabicDate;
        document.getElementById('current-time').textContent = timeStr;
    }

    initEventListeners() {
        // Fullscreen button
        document.getElementById('fullscreen-btn').addEventListener('click', () => {
            this.toggleFullscreen();
        });

        // Refresh button
        document.getElementById('refresh-btn').addEventListener('click', () => {
            this.loadDashboardData();
        });

        // Print button
        document.getElementById('print-btn').addEventListener('click', () => {
            this.printReport();
        });

        // Settings button
        document.getElementById('settings-btn').addEventListener('click', () => {
            const modal = new bootstrap.Modal(document.getElementById('settingsModal'));
            modal.show();
        });

        // Save settings button
        document.getElementById('save-settings').addEventListener('click', () => {
            this.saveSettings();
            const modal = bootstrap.Modal.getInstance(document.getElementById('settingsModal'));
            modal.hide();
        });

        // Handle visibility change (pause refresh when tab is hidden)
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.stopAutoRefresh();
            } else {
                this.startAutoRefresh();
            }
        });
    }

    async loadDashboardData() {
        try {
            const response = await fetch('/api/attendance/monitor/live-status/');
            const result = await response.json();

            if (result.success) {
                this.updateDashboard(result.data);
            } else {
                console.error('Error loading dashboard data:', result.error);
            }
        } catch (error) {
            console.error('Error fetching dashboard data:', error);
        }
    }

    updateDashboard(data) {
        // Update summary
        this.updateSummary(data.summary);

        // Update rooms grid
        this.updateRoomsGrid(data.rooms);

        // Update alerts
        if (this.settings.showAlerts) {
            this.updateAlerts(data.alerts);
        }

        // Store for comparison
        this.lastData = data;
    }

    updateSummary(summary) {
        this.animateNumber('total-present', summary.total_present_today);
        this.animateNumber('active-sessions', summary.active_sessions);
    }

    updateRoomsGrid(rooms) {
        const grid = document.getElementById('rooms-grid');

        // Check if data has changed
        if (this.lastData && JSON.stringify(this.lastData.rooms) === JSON.stringify(rooms)) {
            return; // No change, skip update
        }

        let html = '';

        rooms.forEach(room => {
            html += this.buildRoomCard(room);
        });

        grid.innerHTML = html;

        // Add click listeners to room cards
        document.querySelectorAll('.room-card').forEach(card => {
            card.addEventListener('click', () => {
                const roomId = card.dataset.roomId;
                this.showRoomDetail(roomId);
            });
        });
    }

    buildRoomCard(room) {
        const statusClass = this.getRoomStatusClass(room.status);
        const statusIcon = this.getRoomStatusIcon(room.status);
        const statusText = this.getRoomStatusText(room.status);

        let sessionHtml = '';
        if (room.session) {
            const s = room.session;
            const attendancePercent = s.total > 0 ? Math.round((s.present / s.total) * 100) : 0;

            sessionHtml = `
                <div class="room-session-info">
                    <div class="session-group">
                        <i class="fas fa-users"></i>
                        ${s.group_name}
                    </div>
                    <div class="session-teacher">
                        <i class="fas fa-chalkboard-teacher"></i>
                        ${s.teacher_name}
                    </div>
                    <div class="session-time">
                        <i class="fas fa-clock"></i>
                        ${s.start_time} - ${s.end_time}
                    </div>
                    
                    <div class="attendance-stats">
                        <div class="attendance-main">
                            <span class="attendance-count">${s.present}</span>
                            <span class="attendance-total">/ ${s.total}</span>
                            <span class="attendance-icon">👥</span>
                        </div>
                        <div class="attendance-breakdown">
                            <div class="stat-item present">
                                <i class="fas fa-check-circle"></i>
                                حاضر: ${s.present}
                            </div>
                            <div class="stat-item late">
                                <i class="fas fa-clock"></i>
                                متأخر: ${s.late}
                            </div>
                            <div class="stat-item blocked">
                                <i class="fas fa-ban"></i>
                                محظور: ${s.blocked_total}
                            </div>
                            <div class="stat-item not-arrived">
                                <i class="fas fa-user-clock"></i>
                                لم يحضر: ${s.not_arrived}
                            </div>
                        </div>
                    </div>
                    
                    <div class="room-status-badge ${statusClass}">
                        ${statusIcon} ${statusText}
                    </div>
                </div>
            `;
        } else {
            sessionHtml = `
                <div class="room-empty">
                    <i class="fas fa-door-open"></i>
                    <p>لا توجد جلسة نشطة</p>
                </div>
            `;
        }

        return `
            <div class="room-card ${statusClass}" data-room-id="${room.id}">
                <div class="room-header">
                    <h4 class="room-name">
                        <i class="fas fa-door-closed"></i>
                        ${room.name}
                    </h4>
                    <span class="room-capacity">السعة: ${room.capacity}</span>
                </div>
                ${sessionHtml}
            </div>
        `;
    }

    getRoomStatusClass(status) {
        const classes = {
            'active': 'status-active',
            'low_attendance': 'status-warning',
            'issues': 'status-danger',
            'empty': 'status-empty'
        };
        return classes[status] || 'status-empty';
    }

    getRoomStatusIcon(status) {
        const icons = {
            'active': '🟢',
            'low_attendance': '🟡',
            'issues': '🔴',
            'empty': '⚪'
        };
        return icons[status] || '⚪';
    }

    getRoomStatusText(status) {
        const texts = {
            'active': 'جاري الحصة',
            'low_attendance': 'حضور منخفض',
            'issues': 'مشاكل',
            'empty': 'فارغة'
        };
        return texts[status] || 'غير معروف';
    }

    updateAlerts(alerts) {
        const container = document.getElementById('alerts-container');
        const countBadge = document.getElementById('alerts-count');

        countBadge.textContent = alerts.length;

        if (alerts.length === 0) {
            container.innerHTML = `
                <div class="no-alerts">
                    <i class="fas fa-check-circle text-success"></i>
                    <p>لا توجد تنبيهات</p>
                </div>
            `;
            return;
        }

        let html = '';
        alerts.forEach(alert => {
            const severityClass = alert.severity === 'danger' ? 'alert-danger' : 'alert-warning';
            html += `
                <div class="alert-item ${severityClass}">
                    <div class="alert-icon">
                        <i class="fas ${alert.severity === 'danger' ? 'fa-exclamation-triangle' : 'fa-exclamation-circle'}"></i>
                    </div>
                    <div class="alert-content">
                        <p class="alert-message">${alert.message}</p>
                        <small class="alert-time">${alert.timestamp}</small>
                    </div>
                </div>
            `;
        });

        container.innerHTML = html;
    }

    async showRoomDetail(roomId) {
        try {
            const response = await fetch(`/api/attendance/monitor/room/${roomId}/`);
            const result = await response.json();

            if (result.success) {
                this.displayRoomDetail(result.data);
            }
        } catch (error) {
            console.error('Error loading room detail:', error);
        }
    }

    displayRoomDetail(data) {
        const modal = document.getElementById('roomDetailModal');
        const title = document.getElementById('roomDetailTitle');
        const body = document.getElementById('roomDetailBody');

        title.textContent = `تفاصيل ${data.room.name}`;

        let html = `
            <div class="room-detail-info">
                <h5>${data.session?.group_name || 'لا توجد جلسة'}</h5>
                <p><strong>المدرس:</strong> ${data.session?.teacher_name || '-'}</p>
                <p><strong>الوقت:</strong> ${data.session?.start_time || '-'} - ${data.session?.end_time || '-'}</p>
            </div>
        `;

        if (data.students && data.students.length > 0) {
            html += `
                <div class="students-list">
                    <h6>قائمة الطلاب</h6>
                    <div class="table-responsive">
                        <table class="table table-sm">
                            <thead>
                                <tr>
                                    <th>الاسم</th>
                                    <th>الكود</th>
                                    <th>الحالة</th>
                                    <th>وقت الحضور</th>
                                </tr>
                            </thead>
                            <tbody>
            `;

            data.students.forEach(student => {
                const statusClass = this.getStudentStatusClass(student.status);
                const statusText = this.getStudentStatusText(student.status);

                html += `
                    <tr>
                        <td>${student.name}</td>
                        <td>${student.code}</td>
                        <td><span class="badge ${statusClass}">${statusText}</span></td>
                        <td>${student.check_in_time || '-'}</td>
                    </tr>
                `;
            });

            html += `
                            </tbody>
                        </table>
                    </div>
                </div>
            `;
        }

        body.innerHTML = html;

        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    }

    getStudentStatusClass(status) {
        const classes = {
            'present': 'bg-success',
            'late': 'bg-warning',
            'late_blocked': 'bg-danger',
            'very_late_blocked': 'bg-dark',
            'absent': 'bg-secondary',
            'not_arrived': 'bg-light text-dark'
        };
        return classes[status] || 'bg-secondary';
    }

    getStudentStatusText(status) {
        const texts = {
            'present': 'حاضر',
            'late': 'متأخر',
            'late_blocked': 'محظور (متأخر)',
            'very_late_blocked': 'محظور (متأخر جداً)',
            'absent': 'غائب',
            'not_arrived': 'لم يحضر'
        };
        return texts[status] || status;
    }

    startAutoRefresh() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
        }

        this.refreshTimer = setInterval(() => {
            this.loadDashboardData();
        }, this.refreshInterval);
    }

    stopAutoRefresh() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
        }
    }

    toggleFullscreen() {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen();
        } else {
            document.exitFullscreen();
        }
    }

    async printReport() {
        try {
            const response = await fetch('/api/attendance/monitor/print-report/');
            const result = await response.json();

            if (result.success) {
                // Create print window
                const printWindow = window.open('', '_blank');
                printWindow.document.write(this.generatePrintReport(result.data));
                printWindow.document.close();
                printWindow.print();
            }
        } catch (error) {
            console.error('Error generating print report:', error);
        }
    }

    generatePrintReport(data) {
        return `
            <!DOCTYPE html>
            <html dir="rtl">
            <head>
                <meta charset="UTF-8">
                <title>تقرير الحالة</title>
                <style>
                    body { font-family: Arial, sans-serif; padding: 20px; }
                    h1 { text-align: center; }
                    .summary { display: flex; justify-content: space-around; margin: 20px 0; }
                    .room-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
                    .room-card { border: 1px solid #ccc; padding: 10px; }
                    .footer { text-align: center; margin-top: 20px; color: #666; }
                </style>
            </head>
            <body>
                <h1>تقرير حالة الحضور</h1>
                <p>التاريخ: ${data.print_timestamp}</p>
                <div class="summary">
                    <div>الحاضرون: ${data.summary.total_present_today}</div>
                    <div>الجلسات النشطة: ${data.summary.active_sessions}</div>
                </div>
                <div class="room-grid">
                    ${data.rooms.map(room => `
                        <div class="room-card">
                            <h3>${room.name}</h3>
                            ${room.session ? `
                                <p>المجموعة: ${room.session.group_name}</p>
                                <p>الحضور: ${room.session.present}/${room.session.total}</p>
                            ` : '<p>لا توجد جلسة</p>'}
                        </div>
                    `).join('')}
                </div>
                <div class="footer">${data.generated_by}</div>
            </body>
            </html>
        `;
    }

    enableKioskMode() {
        // Prevent screen sleep
        if ('wakeLock' in navigator) {
            navigator.wakeLock.request('screen').catch(console.error);
        }

        // Hide scrollbars
        document.body.style.overflow = 'hidden';
    }

    disableKioskMode() {
        // Release wake lock
        document.body.style.overflow = '';
    }

    animateNumber(elementId, newValue) {
        const element = document.getElementById(elementId);
        const currentValue = parseInt(element.textContent) || 0;

        if (currentValue === newValue) {
            return;
        }

        // Animate the change
        element.style.transform = 'scale(1.2)';
        element.textContent = newValue;

        setTimeout(() => {
            element.style.transform = 'scale(1)';
        }, 200);
    }

    showToast(message, type = 'info') {
        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            padding: 12px 24px;
            border-radius: 8px;
            color: white;
            font-weight: bold;
            z-index: 9999;
            animation: fadeInOut 3s forwards;
        `;

        if (type === 'success') {
            toast.style.backgroundColor = '#28a745';
        } else if (type === 'error') {
            toast.style.backgroundColor = '#dc3545';
        } else {
            toast.style.backgroundColor = '#17a2b8';
        }

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, 3000);
    }
}

// Add CSS animation for toast
const style = document.createElement('style');
style.textContent = `
    @keyframes fadeInOut {
        0% { opacity: 0; transform: translateX(-50%) translateY(20px); }
        10% { opacity: 1; transform: translateX(-50%) translateY(0); }
        90% { opacity: 1; transform: translateX(-50%) translateY(0); }
        100% { opacity: 0; transform: translateX(-50%) translateY(-20px); }
    }
`;
document.head.appendChild(style);

// Initialize monitor when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.liveMonitor = new LiveMonitor();
});
