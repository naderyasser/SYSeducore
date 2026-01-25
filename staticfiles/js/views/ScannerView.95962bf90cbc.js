/**
 * Scanner View - Handles UI for barcode scanning
 */
class ScannerView {
    
    constructor() {
        this.scannerInput = document.getElementById('scanner-input');
        this.resultContainer = document.getElementById('scan-result');
        this.recentScansContainer = document.getElementById('recent-scans');
        this.sessionInfoContainer = document.getElementById('session-info');
        
        this.successSound = new Audio('/static/sounds/success.mp3');
        this.errorSound = new Audio('/static/sounds/error.mp3');
    }
    
    /**
     * Initialize the view
     */
    init() {
        this.clearScannerInput();
        this.hideResult();
        this.clearRecentScans();
    }
    
    /**
     * Get the scanned barcode value
     */
    getScannedBarcode() {
        return this.scannerInput ? this.scannerInput.value.trim() : '';
    }
    
    /**
     * Clear the scanner input
     */
    clearScannerInput() {
        if (this.scannerInput) {
            this.scannerInput.value = '';
            this.scannerInput.focus();
        }
    }
    
    /**
     * Display scan result
     */
    displayResult(data) {
        if (!this.resultContainer) return;
        
        const isSuccess = data.success;
        const statusClass = isSuccess ? 'status-present' : 'status-absent';
        
        this.resultContainer.innerHTML = `
            <div class="card result-card border-${isSuccess ? 'success' : 'danger'}">
                <div class="card-body text-center">
                    <h4 class="card-title ${statusClass}">
                        ${isSuccess ? '✓ تم الحضور بنجاح' : '✗ فشل الحضور'}
                    </h4>
                    ${data.student ? `
                        <h5 class="card-text">${data.student.name}</h5>
                        <p class="card-text text-muted">${data.student.barcode}</p>
                    ` : ''}
                    ${data.message ? `
                        <p class="card-text ${isSuccess ? 'text-success' : 'text-danger'}">
                            ${data.message}
                        </p>
                    ` : ''}
                    ${data.checks ? this.renderChecks(data.checks) : ''}
                </div>
            </div>
        `;
        
        this.resultContainer.style.display = 'block';
        
        // Play sound
        if (isSuccess) {
            this.successSound.play().catch(() => {});
        } else {
            this.errorSound.play().catch(() => {});
        }
    }
    
    /**
     * Render triple check results
     */
    renderChecks(checks) {
        return `
            <div class="mt-3">
                <h6>نتائج الفحص:</h6>
                <ul class="list-unstyled">
                    <li class="${checks.time ? 'text-success' : 'text-danger'}">
                        ${checks.time ? '✓' : '✗'} التوقيت
                    </li>
                    <li class="${checks.day ? 'text-success' : 'text-danger'}">
                        ${checks.day ? '✓' : '✗'} اليوم
                    </li>
                    <li class="${checks.financial ? 'text-success' : 'text-danger'}">
                        ${checks.financial ? '✓' : '✗'} الحالة المالية
                    </li>
                </ul>
            </div>
        `;
    }
    
    /**
     * Hide result display
     */
    hideResult() {
        if (this.resultContainer) {
            this.resultContainer.style.display = 'none';
        }
    }
    
    /**
     * Add recent scan to the list
     */
    addRecentScan(data) {
        if (!this.recentScansContainer) return;
        
        const scanItem = document.createElement('div');
        scanItem.className = `alert ${data.success ? 'alert-success' : 'alert-danger'} mb-2`;
        scanItem.innerHTML = `
            <strong>${data.student ? data.student.name : 'غير معروف'}</strong>
            <small class="d-block text-muted">${new Date().toLocaleTimeString('ar-EG')}</small>
            ${data.message ? `<small>${data.message}</small>` : ''}
        `;
        
        this.recentScansContainer.insertBefore(scanItem, this.recentScansContainer.firstChild);
        
        // Keep only last 10 scans
        while (this.recentScansContainer.children.length > 10) {
            this.recentScansContainer.removeChild(this.recentScansContainer.lastChild);
        }
    }
    
    /**
     * Clear recent scans
     */
    clearRecentScans() {
        if (this.recentScansContainer) {
            this.recentScansContainer.innerHTML = '';
        }
    }
    
    /**
     * Display session information
     */
    displaySessionInfo(session) {
        if (!this.sessionInfoContainer) return;
        
        this.sessionInfoContainer.innerHTML = `
            <div class="card">
                <div class="card-body">
                    <h5 class="card-title">معلومات الحصة</h5>
                    <p><strong>المجموعة:</strong> ${session.group ? session.group.name : 'غير محدد'}</p>
                    <p><strong>التاريخ:</strong> ${session.formatted_date || '-'}</p>
                    <p><strong>المعلم:</strong> ${session.teacher ? session.teacher.name : 'غير محدد'}</p>
                    <p><strong>الحالة:</strong> ${session.status || '-'}</p>
                </div>
            </div>
        `;
    }
    
    /**
     * Show loading state
     */
    showLoading() {
        if (this.resultContainer) {
            this.resultContainer.innerHTML = `
                <div class="card">
                    <div class="card-body text-center">
                        <div class="spinner-border text-primary" role="status">
                            <span class="sr-only">جاري المعالجة...</span>
                        </div>
                        <p class="mt-2">جاري معالجة الباركود...</p>
                    </div>
                </div>
            `;
            this.resultContainer.style.display = 'block';
        }
    }
    
    /**
     * Show error message
     */
    showError(message) {
        if (this.resultContainer) {
            this.resultContainer.innerHTML = `
                <div class="card result-card border-danger">
                    <div class="card-body text-center">
                        <h4 class="card-title status-absent">✗ خطأ</h4>
                        <p class="card-text text-danger">${message}</p>
                    </div>
                </div>
            `;
            this.resultContainer.style.display = 'block';
        }
    }
}
