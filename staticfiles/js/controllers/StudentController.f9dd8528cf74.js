/**
 * Student Controller - Handles student management logic
 */
class StudentController {
    
    constructor(view, api) {
        this.view = view;
        this.api = api;
        this.students = [];
    }
    
    /**
     * Initialize the controller
     */
    init() {
        this.view.init();
        this.setupEventListeners();
        this.loadStudents();
    }
    
    /**
     * Setup event listeners
     */
    setupEventListeners() {
        const searchInput = document.getElementById('student-search');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.searchStudents(e.target.value);
            });
        }
        
        const createButton = document.getElementById('create-student-button');
        if (createButton) {
            createButton.addEventListener('click', () => {
                this.showCreateForm();
            });
        }
    }
    
    /**
     * Load all students
     */
    async loadStudents() {
        try {
            const response = await this.api.get('/api/students/');
            this.students = response.results || response;
            this.view.displayStudents(this.students);
        } catch (error) {
            console.error('Error loading students:', error);
            this.view.showError('حدث خطأ أثناء تحميل الطلاب');
        }
    }
    
    /**
     * Search students
     */
    searchStudents(query) {
        if (!query) {
            this.view.displayStudents(this.students);
            return;
        }
        
        const filtered = this.students.filter(student => 
            student.name.toLowerCase().includes(query.toLowerCase()) ||
            student.barcode.toLowerCase().includes(query.toLowerCase()) ||
            student.phone.includes(query)
        );
        
        this.view.displayStudents(filtered);
    }
    
    /**
     * Load student details
     */
    async loadStudentDetails(studentId) {
        try {
            const response = await this.api.get(`/api/students/${studentId}/`);
            this.view.displayStudentDetails(response);
        } catch (error) {
            console.error('Error loading student details:', error);
            this.view.showError('حدث خطأ أثناء تحميل تفاصيل الطالب');
        }
    }
    
    /**
     * Load student attendance history
     */
    async loadStudentAttendance(studentId) {
        try {
            const response = await this.api.get(`/api/students/${studentId}/attendance/`);
            this.view.displayAttendanceHistory(response.results || response);
        } catch (error) {
            console.error('Error loading student attendance:', error);
            this.view.showError('حدث خطأ أثناء تحميل سجل الحضور');
        }
    }
    
    /**
     * Show create form
     */
    showCreateForm() {
        this.view.showForm({
            title: 'إضافة طالب جديد',
            student: null,
            mode: 'create'
        });
    }
    
    /**
     * Show edit form
     */
    showEditForm(studentId) {
        const student = this.students.find(s => s.id === studentId);
        if (!student) return;
        
        this.view.showForm({
            title: 'تعديل بيانات الطالب',
            student: student,
            mode: 'edit'
        });
    }
    
    /**
     * Create student
     */
    async createStudent(data) {
        try {
            const response = await this.api.post('/api/students/', data);
            
            if (response.id) {
                alert('تم إضافة الطالب بنجاح');
                this.loadStudents();
                return true;
            } else {
                alert('فشل إضافة الطالب');
                return false;
            }
        } catch (error) {
            console.error('Error creating student:', error);
            alert('حدث خطأ أثناء إضافة الطالب');
            return false;
        }
    }
    
    /**
     * Update student
     */
    async updateStudent(studentId, data) {
        try {
            const response = await this.api.put(`/api/students/${studentId}/`, data);
            
            if (response.id) {
                alert('تم تحديث بيانات الطالب بنجاح');
                this.loadStudents();
                return true;
            } else {
                alert('فشل تحديث بيانات الطالب');
                return false;
            }
        } catch (error) {
            console.error('Error updating student:', error);
            alert('حدث خطأ أثناء تحديث بيانات الطالب');
            return false;
        }
    }
    
    /**
     * Delete student
     */
    async deleteStudent(studentId) {
        if (!confirm('هل أنت متأكد من حذف هذا الطالب؟')) return;
        
        try {
            await this.api.delete(`/api/students/${studentId}/`);
            alert('تم حذف الطالب بنجاح');
            this.loadStudents();
        } catch (error) {
            console.error('Error deleting student:', error);
            alert('حدث خطأ أثناء حذف الطالب');
        }
    }
    
    /**
     * Record payment
     */
    async recordPayment(studentId, month, amount) {
        try {
            const response = await this.api.post('/api/payments/record/', {
                student: studentId,
                month: month,
                amount: amount
            });
            
            if (response.id) {
                alert('تم تسجيل الدفعة بنجاح');
                this.loadStudentDetails(studentId);
                return true;
            } else {
                alert('فشل تسجيل الدفعة');
                return false;
            }
        } catch (error) {
            console.error('Error recording payment:', error);
            alert('حدث خطأ أثناء تسجيل الدفعة');
            return false;
        }
    }
    
    /**
     * Refresh data
     */
    refresh() {
        this.loadStudents();
    }
}
