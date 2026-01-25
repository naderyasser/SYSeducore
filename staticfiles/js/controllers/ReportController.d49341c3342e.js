/**
 * Report Controller - Handles report generation and export
 */
class ReportController {
    
    constructor(view, api) {
        this.view = view;
        this.api = api;
        this.currentReportType = null;
        this.currentData = null;
    }
    
    /**
     * Initialize the controller
     */
    init() {
        this.view.init();
        this.setupEventListeners();
        this.setupFilters();
        this.view.displayExportButtons();
    }
    
    /**
     * Setup event listeners
     */
    setupEventListeners() {
        const reportTypeSelect = document.getElementById('report-type');
        if (reportTypeSelect) {
            reportTypeSelect.addEventListener('change', (e) => {
                this.changeReportType(e.target.value);
            });
        }
        
        const generateButton = document.getElementById('generate-report-button');
        if (generateButton) {
            generateButton.addEventListener('click', () => {
                this.generateReport();
            });
        }
    }
    
    /**
     * Setup report filters
     */
    setupFilters() {
        const filters = [
            {
                id: 'start-date',
                name: 'start_date',
                label: 'من تاريخ',
                type: 'date'
            },
            {
                id: 'end-date',
                name: 'end_date',
                label: 'إلى تاريخ',
                type: 'date'
            },
            {
                id: 'group-filter',
                name: 'group',
                label: 'المجموعة',
                type: 'select',
                options: [
                    { value: '', label: 'الكل' },
                    { value: '1', label: 'المجموعة 1' },
                    { value: '2', label: 'المجموعة 2' }
                ]
            },
            {
                id: 'teacher-filter',
                name: 'teacher',
                label: 'المعلم',
                type: 'select',
                options: [
                    { value: '', label: 'الكل' },
                    { value: '1', label: 'المعلم 1' },
                    { value: '2', label: 'المعلم 2' }
                ]
            }
        ];
        
        this.view.displayFilters(filters);
    }
    
    /**
     * Change report type
     */
    changeReportType(type) {
        this.currentReportType = type;
        this.currentData = null;
        this.view.clear();
    }
    
    /**
     * Generate report
     */
    async generateReport() {
        const filters = this.view.getFilterValues();
        
        if (!this.currentReportType) {
            alert('الرجاء اختيار نوع التقرير');
            return;
        }
        
        this.view.showLoading();
        
        try {
            let response;
            
            switch (this.currentReportType) {
                case 'attendance':
                    response = await this.api.get('/api/reports/attendance/', { params: filters });
                    this.view.displayAttendanceReport(response);
                    break;
                case 'payment':
                    response = await this.api.get('/api/reports/payment/', { params: filters });
                    this.view.displayPaymentReport(response);
                    break;
                case 'settlement':
                    response = await this.api.get('/api/reports/settlement/', { params: filters });
                    this.view.displaySettlementReport(response);
                    break;
                default:
                    alert('نوع التقرير غير صالح');
                    return;
            }
            
            this.currentData = response;
            
        } catch (error) {
            console.error('Error generating report:', error);
            this.view.showError('حدث خطأ أثناء إنشاء التقرير');
        }
    }
    
    /**
     * Export report
     */
    async exportReport(format) {
        if (!this.currentData) {
            alert('الرجاء إنشاء التقرير أولاً');
            return;
        }
        
        const filters = this.view.getFilterValues();
        
        try {
            const response = await this.api.get(`/api/reports/export/${format}/`, { 
                params: {
                    ...filters,
                    report_type: this.currentReportType
                }
            });
            
            if (response.file_url) {
                // Download the file
                const link = document.createElement('a');
                link.href = response.file_url;
                link.download = response.filename;
                link.click();
            } else {
                alert('فشل تصدير التقرير');
            }
        } catch (error) {
            console.error('Error exporting report:', error);
            alert('حدث خطأ أثناء تصدير التقرير');
        }
    }
    
    /**
     * Print report
     */
    printReport() {
        if (!this.currentData) {
            alert('الرجاء إنشاء التقرير أولاً');
            return;
        }
        
        window.print();
    }
    
    /**
     * Refresh report
     */
    refresh() {
        this.generateReport();
    }
}

/**
 * Export report function (global)
 */
function exportReport(format) {
    if (window.reportController) {
        window.reportController.exportReport(format);
    }
}
