/**
 * Dashboard View - Handles UI for dashboard statistics
 */
class DashboardView {
    
    constructor() {
        this.statsContainer = document.getElementById('stats-container');
        this.recentActivityContainer = document.getElementById('recent-activity');
        this.upcomingSessionsContainer = document.getElementById('upcoming-sessions');
    }
    
    /**
     * Initialize the view
     */
    init() {
        this.showLoading();
    }
    
    /**
     * Display statistics
     */
    displayStats(stats) {
        if (!this.statsContainer) return;
        
        this.statsContainer.innerHTML = `
            <div class="row">
                <div class="col-md-3">
                    <div class="card bg-primary text-white">
                        <div class="card-body">
                            <h5 class="card-title">إجمالي الطلاب</h5>
                            <h2 class="display-4">${stats.total_students || 0}</h2>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card bg-success text-white">
                        <div class="card-body">
                            <h5 class="card-title">حضور اليوم</h5>
                            <h2 class="display-4">${stats.today_attendance || 0}</h2>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card bg-warning text-dark">
                        <div class="card-body">
                            <h5 class="card-title">المجموعات النشطة</h5>
                            <h2 class="display-4">${stats.active_groups || 0}</h2>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card bg-info text-white">
                        <div class="card-body">
                            <h5 class="card-title">المعلمين</h5>
                            <h2 class="display-4">${stats.total_teachers || 0}</h2>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    /**
     * Display financial statistics
     */
    displayFinancialStats(stats) {
        if (!this.statsContainer) return;
        
        const financialContainer = document.createElement('div');
        financialContainer.className = 'row mt-4';
        financialContainer.innerHTML = `
            <div class="col-md-4">
                <div class="card bg-secondary text-white">
                    <div class="card-body">
                        <h5 class="card-title">إيرادات الشهر</h5>
                        <h3>${stats.monthly_revenue || 0} ج.م</h3>
                    </div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card bg-danger text-white">
                    <div class="card-body">
                        <h5 class="card-title">المدفوعات المستحقة</h5>
                        <h3>${stats.pending_payments || 0} ج.م</h3>
                    </div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card bg-success text-white">
                    <div class="card-body">
                        <h5 class="card-title">المدفوعات المحصلة</h5>
                        <h3>${stats.collected_payments || 0} ج.م</h3>
                    </div>
                </div>
            </div>
        `;
        
        this.statsContainer.appendChild(financialContainer);
    }
    
    /**
     * Display recent activity
     */
    displayRecentActivity(activities) {
        if (!this.recentActivityContainer) return;
        
        if (!activities || activities.length === 0) {
            this.recentActivityContainer.innerHTML = '<p class="text-muted">لا توجد نشاطات حديثة</p>';
            return;
        }
        
        this.recentActivityContainer.innerHTML = activities.map(activity => `
            <div class="alert ${this.getActivityAlertClass(activity.type)} mb-2">
                <strong>${activity.title}</strong>
                <small class="d-block text-muted">${activity.time}</small>
                ${activity.description ? `<small>${activity.description}</small>` : ''}
            </div>
        `).join('');
    }
    
    /**
     * Get alert class based on activity type
     */
    getActivityAlertClass(type) {
        switch (type) {
            case 'attendance':
                return 'alert-success';
            case 'payment':
                return 'alert-info';
            case 'absence':
                return 'alert-warning';
            case 'error':
                return 'alert-danger';
            default:
                return 'alert-secondary';
        }
    }
    
    /**
     * Display upcoming sessions
     */
    displayUpcomingSessions(sessions) {
        if (!this.upcomingSessionsContainer) return;
        
        if (!sessions || sessions.length === 0) {
            this.upcomingSessionsContainer.innerHTML = '<p class="text-muted">لا توجد حصص قادمة</p>';
            return;
        }
        
        this.upcomingSessionsContainer.innerHTML = sessions.map(session => `
            <div class="card mb-2">
                <div class="card-body">
                    <h6 class="card-title">${session.group_name || 'غير محدد'}</h6>
                    <p class="card-text mb-0">
                        <small class="text-muted">
                            <i class="fas fa-calendar"></i> ${session.date || '-'}
                            <i class="fas fa-clock"></i> ${session.time || '-'}
                        </small>
                    </p>
                    <p class="card-text mb-0">
                        <small class="text-muted">
                            <i class="fas fa-user"></i> ${session.teacher_name || 'غير محدد'}
                        </small>
                    </p>
                </div>
            </div>
        `).join('');
    }
    
    /**
     * Show loading state
     */
    showLoading() {
        if (this.statsContainer) {
            this.statsContainer.innerHTML = `
                <div class="text-center">
                    <div class="spinner-border text-primary" role="status">
                        <span class="sr-only">جاري التحميل...</span>
                    </div>
                </div>
            `;
        }
    }
    
    /**
     * Show error message
     */
    showError(message) {
        if (this.statsContainer) {
            this.statsContainer.innerHTML = `
                <div class="alert alert-danger">
                    ${message}
                </div>
            `;
        }
    }
    
    /**
     * Clear all displays
     */
    clear() {
        if (this.statsContainer) {
            this.statsContainer.innerHTML = '';
        }
        if (this.recentActivityContainer) {
            this.recentActivityContainer.innerHTML = '';
        }
        if (this.upcomingSessionsContainer) {
            this.upcomingSessionsContainer.innerHTML = '';
        }
    }
}
