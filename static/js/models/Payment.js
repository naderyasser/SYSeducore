/**
 * Payment Model
 */
class Payment {
    
    constructor(data = {}) {
        this.id = data.id || null;
        this.student = data.student || null; // Student object
        this.month = data.month || '';
        this.amount_due = data.amount_due || 0;
        this.amount_paid = data.amount_paid || 0;
        this.status = data.status || 'unpaid'; // unpaid, partial, paid
        this.sessions_attended = data.sessions_attended || 0;
        this.created_at = data.created_at || new Date();
        this.updated_at = data.updated_at || new Date();
    }
    
    /**
     * Get remaining amount
     */
    getRemainingAmount() {
        return this.amount_due - this.amount_paid;
    }
    
    /**
     * Get status label in Arabic
     */
    getStatusLabel() {
        switch (this.status) {
            case 'partial':
                return 'مدفوع جزئياً';
            case 'paid':
                return 'مدفوع';
            case 'unpaid':
            default:
                return 'غير مدفوع';
        }
    }
    
    /**
     * Get status CSS class
     */
    getStatusClass() {
        switch (this.status) {
            case 'partial':
                return 'status-late';
            case 'paid':
                return 'status-present';
            case 'unpaid':
            default:
                return 'status-absent';
        }
    }
    
    /**
     * Check if payment is complete
     */
    isPaid() {
        return this.amount_paid >= this.amount_due;
    }
    
    /**
     * Check if payment is partial
     */
    isPartial() {
        return this.amount_paid > 0 && this.amount_paid < this.amount_due;
    }
    
    /**
     * Update payment status
     */
    updateStatus() {
        if (this.isPaid()) {
            this.status = 'paid';
        } else if (this.isPartial()) {
            this.status = 'partial';
        } else {
            this.status = 'unpaid';
        }
    }
    
    /**
     * Get formatted month
     */
    getFormattedMonth() {
        if (!this.month) return '-';
        
        const months = [
            'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
            'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'
        ];
        
        const [year, month] = this.month.split('-');
        return `${months[parseInt(month) - 1]} ${year}`;
    }
    
    /**
     * Convert to JSON
     */
    toJSON() {
        return {
            id: this.id,
            student: this.student,
            month: this.month,
            amount_due: this.amount_due,
            amount_paid: this.amount_paid,
            status: this.status,
            sessions_attended: this.sessions_attended,
            created_at: this.created_at,
            updated_at: this.updated_at
        };
    }
    
    /**
     * Create Payment from JSON
     */
    static fromJSON(json) {
        return new Payment(json);
    }
}

/**
 * Teacher Settlement Model
 */
class TeacherSettlement {
    
    constructor(data = {}) {
        this.teacher = data.teacher || null; // Teacher object
        this.group = data.group || null; // Group object
        this.month = data.month || '';
        this.total_sessions = data.total_sessions || 0;
        this.total_students = data.total_students || 0;
        this.total_revenue = data.total_revenue || 0;
        this.center_percentage = data.center_percentage || 30;
        this.center_share = data.center_share || 0;
        this.teacher_share = data.teacher_share || 0;
    }
    
    /**
     * Calculate settlement
     */
    calculate() {
        this.center_share = this.total_revenue * (this.center_percentage / 100);
        this.teacher_share = this.total_revenue - this.center_share;
    }
    
    /**
     * Get formatted month
     */
    getFormattedMonth() {
        if (!this.month) return '-';
        
        const months = [
            'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
            'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'
        ];
        
        const [year, month] = this.month.split('-');
        return `${months[parseInt(month) - 1]} ${year}`;
    }
    
    /**
     * Convert to JSON
     */
    toJSON() {
        return {
            teacher: this.teacher,
            group: this.group,
            month: this.month,
            total_sessions: this.total_sessions,
            total_students: this.total_students,
            total_revenue: this.total_revenue,
            center_percentage: this.center_percentage,
            center_share: this.center_share,
            teacher_share: this.teacher_share
        };
    }
    
    /**
     * Create TeacherSettlement from JSON
     */
    static fromJSON(json) {
        return new TeacherSettlement(json);
    }
}
