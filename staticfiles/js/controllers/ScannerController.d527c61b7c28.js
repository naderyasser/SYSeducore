/**
 * Scanner Controller - Handles barcode scanning logic
 */
class ScannerController {
    
    constructor(view, api) {
        this.view = view;
        this.api = api;
        this.isProcessing = false;
        this.currentSessionId = null;
    }
    
    /**
     * Initialize the controller
     */
    init() {
        this.view.init();
        this.setupEventListeners();
        this.loadSessionInfo();
    }
    
    /**
     * Setup event listeners
     */
    setupEventListeners() {
        const scannerInput = document.getElementById('scanner-input');
        if (scannerInput) {
            scannerInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.handleScan();
                }
            });
        }
    }
    
    /**
     * Load session information
     */
    async loadSessionInfo() {
        try {
            const sessionId = this.getSessionId();
            if (!sessionId) return;
            
            const response = await this.api.get(`/api/attendance/session/${sessionId}/`);
            this.view.displaySessionInfo(response);
        } catch (error) {
            console.error('Error loading session info:', error);
        }
    }
    
    /**
     * Get session ID from URL
     */
    getSessionId() {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('session_id');
    }
    
    /**
     * Handle barcode scan
     */
    async handleScan() {
        if (this.isProcessing) return;
        
        const barcode = this.view.getScannedBarcode();
        if (!barcode) return;
        
        this.isProcessing = true;
        this.view.showLoading();
        
        try {
            const response = await this.api.post('/api/attendance/scan/', {
                barcode: barcode,
                session_id: this.getSessionId()
            });
            
            this.view.displayResult(response);
            this.view.addRecentScan(response);
            this.view.clearScannerInput();
            
        } catch (error) {
            console.error('Scan error:', error);
            this.view.showError(error.message || 'حدث خطأ أثناء معالجة الباركود');
        } finally {
            this.isProcessing = false;
        }
    }
    
    /**
     * Record teacher attendance
     */
    async recordTeacherAttendance(sessionId) {
        try {
            const response = await this.api.post(`/api/attendance/session/${sessionId}/teacher-attendance/`, {});
            
            if (response.success) {
                alert('تم تسجيل حضور المعلم بنجاح');
                this.loadSessionInfo();
            } else {
                alert('فشل تسجيل حضور المعلم');
            }
        } catch (error) {
            console.error('Error recording teacher attendance:', error);
            alert('حدث خطأ أثناء تسجيل حضور المعلم');
        }
    }
    
    /**
     * Cancel session
     */
    async cancelSession(sessionId) {
        if (!confirm('هل أنت متأكد من إلغاء الحصة؟')) return;
        
        try {
            const response = await this.api.post(`/api/attendance/session/${sessionId}/cancel/`, {});
            
            if (response.success) {
                alert('تم إلغاء الحصة بنجاح');
                this.loadSessionInfo();
            } else {
                alert('فشل إلغاء الحصة');
            }
        } catch (error) {
            console.error('Error cancelling session:', error);
            alert('حدث خطأ أثناء إلغاء الحصة');
        }
    }
    
    /**
     * Refresh session data
     */
    refresh() {
        this.loadSessionInfo();
    }
}
