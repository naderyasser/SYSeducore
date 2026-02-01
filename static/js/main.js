/**
 * Main JavaScript file for EDUCORE V2
 * HTMX + Alpine.js integration
 */

// ============================================
// Alpine.js Global Data Store
// ============================================
function appData() {
    return {
        // Toast notifications
        toasts: [],
        toastIdCounter: 0,

        // Online status
        isOnline: navigator.onLine,

        // CSRF Token
        csrfToken: document.querySelector('meta[name="csrf-token"]')?.content || '',

        // ========================================
        // Toast Methods
        // ========================================
        showToast(message, type = 'info', title = '', duration = 5000) {
            const id = ++this.toastIdCounter;
            const icons = {
                success: 'bi bi-check-circle-fill text-success',
                error: 'bi bi-x-circle-fill text-danger',
                warning: 'bi bi-exclamation-triangle-fill text-warning',
                info: 'bi bi-info-circle-fill text-info'
            };
            const titles = {
                success: title || 'نجاح',
                error: title || 'خطأ',
                warning: title || 'تحذير',
                info: title || 'معلومات'
            };

            this.toasts.push({
                id,
                message,
                type,
                title: titles[type],
                icon: icons[type]
            });

            // Auto-remove after duration
            if (duration > 0) {
                setTimeout(() => {
                    this.removeToast(id);
                }, duration);
            }

            return id;
        },

        removeToast(id) {
            this.toasts = this.toasts.filter(t => t.id !== id);
        },

        // ========================================
        // Utility Methods
        // ========================================
        formatDate(date, format = 'short') {
            const d = new Date(date);
            const options = {
                short: { year: 'numeric', month: '2-digit', day: '2-digit' },
                long: { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' },
                time: { hour: '2-digit', minute: '2-digit' }
            };
            return d.toLocaleDateString('ar-EG', options[format] || options.short);
        },

        formatCurrency(amount) {
            return new Intl.NumberFormat('ar-EG', {
                style: 'currency',
                currency: 'EGP'
            }).format(amount);
        },

        formatNumber(num) {
            return new Intl.NumberFormat('ar-EG').format(num);
        },

        // ========================================
        // API Client (for non-HTMX requests)
        // ========================================
        async apiRequest(url, options = {}) {
            const defaults = {
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                }
            };

            const config = { ...defaults, ...options };

            try {
                const response = await fetch(url, config);
                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.message || 'حدث خطأ في الطلب');
                }

                return data;
            } catch (error) {
                this.showToast(error.message, 'error');
                throw error;
            }
        },

        async get(url) {
            return this.apiRequest(url, { method: 'GET' });
        },

        async post(url, data) {
            return this.apiRequest(url, {
                method: 'POST',
                body: JSON.stringify(data)
            });
        },

        async put(url, data) {
            return this.apiRequest(url, {
                method: 'PUT',
                body: JSON.stringify(data)
            });
        },

        async delete(url) {
            return this.apiRequest(url, { method: 'DELETE' });
        },

        // ========================================
        // Initialize
        // ========================================
        init() {
            // Online/offline detection
            window.addEventListener('online', () => {
                this.isOnline = true;
                this.showToast('تم استعادة الاتصال', 'success');
            });

            window.addEventListener('offline', () => {
                this.isOnline = false;
                this.showToast('فقدان الاتصال بالإنترنت', 'warning');
            });

            // Setup HTMX event listeners
            this.setupHtmxEvents();
        },

        setupHtmxEvents() {
            // HTMX request error handling
            document.body.addEventListener('htmx:responseError', (event) => {
                const xhr = event.detail.xhr;
                let message = 'حدث خطأ في الطلب';

                try {
                    const data = JSON.parse(xhr.responseText);
                    message = data.message || message;
                } catch (e) {
                    message = xhr.statusText || message;
                }

                this.showToast(message, 'error');
            });

            // HTMX before request - show loading
            document.body.addEventListener('htmx:beforeRequest', (event) => {
                const target = event.detail.target;
                if (target) {
                    target.classList.add('htmx-loading');
                }
            });

            // HTMX after request - hide loading
            document.body.addEventListener('htmx:afterRequest', (event) => {
                const target = event.detail.target;
                if (target) {
                    target.classList.remove('htmx-loading');
                }
            });

            // HTMX success - show toast if message in response
            document.body.addEventListener('htmx:afterSwap', (event) => {
                const xhr = event.detail.xhr;
                try {
                    const data = JSON.parse(xhr.responseText);
                    if (data.message) {
                        this.showToast(data.message, data.success ? 'success' : 'info');
                    }
                } catch (e) {
                    // Not JSON response, ignore
                }
            });
        }
    };
}

// ============================================
// Alpine.js Components
// ============================================

// Barcode Scanner Component
function scannerData() {
    return {
        barcode: '',
        isProcessing: false,
        recentScans: [],
        maxRecentScans: 10,

        init() {
            // Focus on barcode input
            this.$nextTick(() => {
                this.$refs.barcodeInput?.focus();
            });

            // Listen for barcode scanner input (usually ends with Enter)
            this.$watch('barcode', (value) => {
                if (value.length > 0) {
                    // Auto-submit when Enter is pressed (handled by form)
                }
            });
        },

        clearInput() {
            this.barcode = '';
            this.$refs.barcodeInput?.focus();
        },

        addRecentScan(scan) {
            this.recentScans.unshift(scan);
            if (this.recentScans.length > this.maxRecentScans) {
                this.recentScans.pop();
            }
        },

        getStatusBadgeClass(status) {
            const classes = {
                present: 'bg-success',
                late: 'bg-warning text-dark',
                absent: 'bg-danger',
                blocked: 'bg-secondary'
            };
            return classes[status] || 'bg-secondary';
        },

        getStatusText(status) {
            const texts = {
                present: 'حاضر',
                late: 'متأخر',
                absent: 'غائب',
                blocked: 'ممنوع'
            };
            return texts[status] || status;
        }
    };
}

// Student Search Component (with autocomplete)
function studentSearchData() {
    return {
        query: '',
        results: [],
        isLoading: false,
        selectedIndex: -1,

        async search() {
            if (this.query.length < 2) {
                this.results = [];
                return;
            }

            this.isLoading = true;

            try {
                const response = await fetch(
                    `/api/students/search/?q=${encodeURIComponent(this.query)}`
                );
                const data = await response.json();
                this.results = data.results || [];
                this.selectedIndex = -1;
            } catch (error) {
                console.error('Search error:', error);
            } finally {
                this.isLoading = false;
            }
        },

        selectStudent(student) {
            this.query = student.full_name;
            this.results = [];
            // Emit custom event or call callback
            this.$dispatch('student-selected', { student });
        },

        clearSearch() {
            this.query = '';
            this.results = [];
        },

        moveSelection(direction) {
            if (direction === 'down') {
                this.selectedIndex = Math.min(this.selectedIndex + 1, this.results.length - 1);
            } else {
                this.selectedIndex = Math.max(this.selectedIndex - 1, -1);
            }
        },

        selectHighlighted() {
            if (this.selectedIndex >= 0 && this.results[this.selectedIndex]) {
                this.selectStudent(this.results[this.selectedIndex]);
            }
        }
    };
}

// Payment Status Component
function paymentStatusData() {
    return {
        payments: [],
        isLoading: false,

        async loadPayments(studentId) {
            this.isLoading = true;
            try {
                const response = await fetch(`/api/payments/student/${studentId}/`);
                const data = await response.json();
                this.payments = data.payments || [];
            } catch (error) {
                console.error('Error loading payments:', error);
            } finally {
                this.isLoading = false;
            }
        },

        getStatusClass(status) {
            const classes = {
                paid: 'text-success',
                partial: 'text-warning',
                unpaid: 'text-danger'
            };
            return classes[status] || 'text-muted';
        },

        getStatusText(status) {
            const texts = {
                paid: 'مدفوع',
                partial: 'مدفوع جزئياً',
                unpaid: 'غير مدفوع'
            };
            return texts[status] || status;
        }
    };
}

// ============================================
// Utility Functions
// ============================================

/**
 * Play sound effect
 * @param {string} type - 'success' or 'error'
 */
function playSound(type) {
    const sounds = {
        success: '/static/sounds/success.mp3',
        error: '/static/sounds/error.mp3'
    };

    const audio = new Audio(sounds[type]);
    audio.volume = 0.3;
    audio.play().catch(e => console.log('Audio play failed:', e));
}

/**
 * Debounce function for search inputs
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Format seconds to HH:MM:SS
 */
function formatDuration(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

// ============================================
// Initialize on DOM ready
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    // Initialize is handled by Alpine.js
    console.log('EDUCORE V2 - HTMX + Alpine.js initialized');
});
