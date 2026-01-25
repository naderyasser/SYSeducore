/**
 * Attendance Model
 */
class Attendance {
    
    constructor(data = {}) {
        this.id = data.id || null;
        this.student = data.student || null; // Student object
        this.session = data.session || null; // Session object
        this.scan_time = data.scan_time || new Date();
        this.status = data.status || 'present'; // present, late, absent
        this.notes = data.notes || '';
        this.created_at = data.created_at || new Date();
        this.updated_at = data.updated_at || new Date();
    }
    
    /**
     * Get status label in Arabic
     */
    getStatusLabel() {
        switch (this.status) {
            case 'late':
                return 'متأخر';
            case 'absent':
                return 'غائب';
            case 'present':
            default:
                return 'حاضر';
        }
    }
    
    /**
     * Get status CSS class
     */
    getStatusClass() {
        switch (this.status) {
            case 'late':
                return 'status-late';
            case 'absent':
                return 'status-absent';
            case 'present':
            default:
                return 'status-present';
        }
    }
    
    /**
     * Get formatted scan time
     */
    getFormattedScanTime() {
        if (!this.scan_time) return '-';
        
        const date = new Date(this.scan_time);
        const hours = date.getHours().toString().padStart(2, '0');
        const minutes = date.getMinutes().toString().padStart(2, '0');
        const seconds = date.getSeconds().toString().padStart(2, '0');
        
        return `${hours}:${minutes}:${seconds}`;
    }
    
    /**
     * Get formatted date
     */
    getFormattedDate() {
        if (!this.scan_time) return '-';
        
        const date = new Date(this.scan_time);
        const day = date.getDate().toString().padStart(2, '0');
        const month = (date.getMonth() + 1).toString().padStart(2, '0');
        const year = date.getFullYear();
        
        return `${day}/${month}/${year}`;
    }
    
    /**
     * Check if attendance is late based on session time
     */
    isLate(sessionStartTime, gracePeriod = 15) {
        if (!this.scan_time || !sessionStartTime) return false;
        
        const scanTime = new Date(this.scan_time);
        const startTime = new Date(sessionStartTime);
        const graceTime = new Date(startTime.getTime() + gracePeriod * 60000);
        
        return scanTime > graceTime;
    }
    
    /**
     * Convert to JSON
     */
    toJSON() {
        return {
            id: this.id,
            student: this.student,
            session: this.session,
            scan_time: this.scan_time,
            status: this.status,
            notes: this.notes,
            created_at: this.created_at,
            updated_at: this.updated_at
        };
    }
    
    /**
     * Create Attendance from JSON
     */
    static fromJSON(json) {
        return new Attendance(json);
    }
}

/**
 * Session Model
 */
class Session {
    
    constructor(data = {}) {
        this.id = data.id || null;
        this.group = data.group || null; // Group object
        this.session_date = data.session_date || new Date();
        this.teacher_attended = data.teacher_attended || false;
        this.notification_sent = data.notification_sent || false;
        this.is_cancelled = data.is_cancelled || false;
        this.created_at = data.created_at || new Date();
        this.updated_at = data.updated_at || new Date();
    }
    
    /**
     * Get formatted session date
     */
    getFormattedDate() {
        if (!this.session_date) return '-';
        
        const date = new Date(this.session_date);
        const day = date.getDate().toString().padStart(2, '0');
        const month = (date.getMonth() + 1).toString().padStart(2, '0');
        const year = date.getFullYear();
        
        return `${day}/${month}/${year}`;
    }
    
    /**
     * Get session status
     */
    getStatus() {
        if (this.is_cancelled) {
            return 'ملغي';
        }
        if (this.teacher_attended) {
            return 'تمت';
        }
        return 'قيد الانتظار';
    }
    
    /**
     * Convert to JSON
     */
    toJSON() {
        return {
            id: this.id,
            group: this.group,
            session_date: this.session_date,
            teacher_attended: this.teacher_attended,
            notification_sent: this.notification_sent,
            is_cancelled: this.is_cancelled,
            created_at: this.created_at,
            updated_at: this.updated_at
        };
    }
    
    /**
     * Create Session from JSON
     */
    static fromJSON(json) {
        return new Session(json);
    }
}
