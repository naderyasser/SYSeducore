/**
 * Student Model
 */
class Student {
    
    constructor(data = {}) {
        this.id = data.id || null;
        this.name = data.name || '';
        this.phone = data.phone || '';
        this.parent_phone = data.parent_phone || '';
        this.group = data.group || null;
        this.financial_status = data.financial_status || 'normal'; // normal, symbolic, exempt
        this.barcode = data.barcode || '';
        this.created_at = data.created_at || new Date();
        this.updated_at = data.updated_at || new Date();
    }
    
    /**
     * Get monthly fee based on financial status
     */
    getMonthlyFee() {
        switch (this.financial_status) {
            case 'symbolic':
                return 100; // Symbolic fee
            case 'exempt':
                return 0;   // Exempt from payment
            case 'normal':
            default:
                return 300; // Normal fee
        }
    }
    
    /**
     * Get financial status label in Arabic
     */
    getFinancialStatusLabel() {
        switch (this.financial_status) {
            case 'symbolic':
                return 'رمزي';
            case 'exempt':
                return 'معفى';
            case 'normal':
            default:
                return 'عادي';
        }
    }
    
    /**
     * Check if student can attend based on financial status
     */
    canAttend(unpaidSessions) {
        if (this.financial_status === 'exempt') {
            return { can: true, reason: null };
        }
        
        if (unpaidSessions >= 3) {
            return { 
                can: false, 
                reason: 'تم تجاوز الحد المسموح (3 حصص) بدون دفع' 
            };
        }
        
        return { can: true, reason: null };
    }
    
    /**
     * Validate student data
     */
    validate() {
        const errors = [];
        
        if (!this.name || this.name.trim() === '') {
            errors.push('الاسم مطلوب');
        }
        
        if (!this.phone || this.phone.trim() === '') {
            errors.push('رقم الهاتف مطلوب');
        }
        
        if (!this.barcode || this.barcode.trim() === '') {
            errors.push('الباركود مطلوب');
        }
        
        if (this.financial_status === 'symbolic' && !this.parent_phone) {
            errors.push('رقم هاتف ولي الأمر مطلوب للحالة الرمزية');
        }
        
        return {
            isValid: errors.length === 0,
            errors: errors
        };
    }
    
    /**
     * Convert to JSON
     */
    toJSON() {
        return {
            id: this.id,
            name: this.name,
            phone: this.phone,
            parent_phone: this.parent_phone,
            group: this.group,
            financial_status: this.financial_status,
            barcode: this.barcode,
            created_at: this.created_at,
            updated_at: this.updated_at
        };
    }
    
    /**
     * Create Student from JSON
     */
    static fromJSON(json) {
        return new Student(json);
    }
}
