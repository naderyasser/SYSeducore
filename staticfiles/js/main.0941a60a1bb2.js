/**
 * Main Application Entry Point
 * Initializes the MVC pattern and sets up the application
 */

// Import models
// Note: In a real project, these would be ES6 modules
// For now, we assume they are loaded via script tags

// Global application state
const App = {
    currentView: null,
    currentController: null,
    user: null,
    
    /**
     * Initialize the application
     */
    init() {
        this.detectPage();
        this.loadCurrentUser();
        this.setupGlobalEventListeners();
    },
    
    /**
     * Detect current page and initialize appropriate controller
     */
    detectPage() {
        const path = window.location.pathname;
        
        if (path === '/' || path === '/dashboard/') {
            this.initDashboard();
        } else if (path.includes('/attendance/scanner')) {
            this.initScanner();
        } else if (path.includes('/students/')) {
            this.initStudents();
        } else if (path.includes('/reports/')) {
            this.initReports();
        } else if (path.includes('/login/')) {
            this.initLogin();
        }
    },
    
    /**
     * Initialize dashboard
     */
    initDashboard() {
        const view = new DashboardView();
        const controller = new DashboardController(view, API);
        
        this.currentView = view;
        this.currentController = controller;
        
        controller.init();
    },
    
    /**
     * Initialize scanner
     */
    initScanner() {
        const view = new ScannerView();
        const controller = new ScannerController(view, API);
        
        this.currentView = view;
        this.currentController = controller;
        
        controller.init();
    },
    
    /**
     * Initialize students page
     */
    initStudents() {
        const view = new StudentView();
        const controller = new StudentController(view, API);
        
        this.currentView = view;
        this.currentController = controller;
        
        controller.init();
    },
    
    /**
     * Initialize reports page
     */
    initReports() {
        const view = new ReportView();
        const controller = new ReportController(view, API);
        
        this.currentView = view;
        this.currentController = controller;
        
        controller.init();
        
        // Make controller globally available for export functions
        window.reportController = controller;
    },
    
    /**
     * Initialize login page
     */
    initLogin() {
        const loginForm = document.getElementById('login-form');
        if (loginForm) {
            loginForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.handleLogin();
            });
        }
    },
    
    /**
     * Handle login
     */
    async handleLogin() {
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;
        
        try {
            const response = await API.post('/api/auth/login/', {
                username: username,
                password: password
            });
            
            if (response.success) {
                window.location.href = '/dashboard/';
            } else {
                alert('اسم المستخدم أو كلمة المرور غير صحيحة');
            }
        } catch (error) {
            console.error('Login error:', error);
            alert('حدث خطأ أثناء تسجيل الدخول');
        }
    },
    
    /**
     * Handle logout
     */
    async handleLogout() {
        try {
            await API.post('/api/auth/logout/', {});
            window.location.href = '/login/';
        } catch (error) {
            console.error('Logout error:', error);
            window.location.href = '/login/';
        }
    },
    
    /**
     * Load current user
     */
    async loadCurrentUser() {
        try {
            const response = await API.get('/api/auth/user/');
            this.user = response;
            this.updateUIForUser();
        } catch (error) {
            // User not logged in
            this.user = null;
        }
    },
    
    /**
     * Update UI based on user role
     */
    updateUIForUser() {
        if (!this.user) return;
        
        // Show/hide elements based on user role
        const adminElements = document.querySelectorAll('.admin-only');
        const supervisorElements = document.querySelectorAll('.supervisor-only');
        const teacherElements = document.querySelectorAll('.teacher-only');
        
        if (this.user.role === 'admin') {
            adminElements.forEach(el => el.style.display = 'block');
            supervisorElements.forEach(el => el.style.display = 'block');
        } else if (this.user.role === 'supervisor') {
            adminElements.forEach(el => el.style.display = 'none');
            supervisorElements.forEach(el => el.style.display = 'block');
        } else if (this.user.role === 'teacher') {
            adminElements.forEach(el => el.style.display = 'none');
            supervisorElements.forEach(el => el.style.display = 'none');
        }
        
        teacherElements.forEach(el => el.style.display = 'block');
    },
    
    /**
     * Setup global event listeners
     */
    setupGlobalEventListeners() {
        // Logout button
        const logoutButton = document.getElementById('logout-button');
        if (logoutButton) {
            logoutButton.addEventListener('click', () => {
                this.handleLogout();
            });
        }
        
        // Session timeout warning
        this.setupSessionTimeout();
    },
    
    /**
     * Setup session timeout
     */
    setupSessionTimeout() {
        const sessionTimeout = 60 * 60 * 1000; // 1 hour
        const warningTime = 5 * 60 * 1000; // 5 minutes before timeout
        
        let warningShown = false;
        
        setTimeout(() => {
            if (!warningShown) {
                warningShown = true;
                alert('جاري انتهاء الجلسة بعد 5 دقائق');
            }
        }, sessionTimeout - warningTime);
        
        setTimeout(() => {
            alert('تم انتهاء الجلسة');
            this.handleLogout();
        }, sessionTimeout);
    },
    
    /**
     * Refresh current page data
     */
    refresh() {
        if (this.currentController) {
            this.currentController.refresh();
        }
    }
};

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    App.init();
});

// Export App for global access
window.App = App;
