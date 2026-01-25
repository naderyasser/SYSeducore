/**
 * Report View - Handles UI for reports
 */
class ReportView {
    
    constructor() {
        this.reportContainer = document.getElementById('report-container');
        this.reportTable = document.getElementById('report-table');
        this.reportFilters = document.getElementById('report-filters');
        this.exportButtons = document.getElementById('export-buttons');
    }
    
    /**
     * Initialize the view
     */
    init() {
        this.showLoading();
    }
    
    /**
     * Display attendance report
     */
    displayAttendanceReport(data) {
        if (!this.reportTable) return;
        
        const { headers, rows, summary } = data;
        
        this.reportTable.innerHTML = `
            <thead>
                <tr>
                    ${headers.map(header => `<th>${header}</th>`).join('')}
                </tr>
            </thead>
            <tbody>
                ${rows.map(row => `
                    <tr>
                        ${row.map(cell => `<td>${cell}</td>`).join('')}
                    </tr>
                `).join('')}
            </tbody>
        `;
        
        if (summary) {
            this.displaySummary(summary);
        }
    }
    
    /**
     * Display payment report
     */
    displayPaymentReport(data) {
        if (!this.reportTable) return;
        
        const { headers, rows, summary } = data;
        
        this.reportTable.innerHTML = `
            <thead>
                <tr>
                    ${headers.map(header => `<th>${header}</th>`).join('')}
                </tr>
            </thead>
            <tbody>
                ${rows.map(row => `
                    <tr>
                        ${row.map(cell => `<td>${cell}</td>`).join('')}
                    </tr>
                `).join('')}
            </tbody>
        `;
        
        if (summary) {
            this.displaySummary(summary);
        }
    }
    
    /**
     * Display teacher settlement report
     */
    displaySettlementReport(data) {
        if (!this.reportTable) return;
        
        const { headers, rows, summary } = data;
        
        this.reportTable.innerHTML = `
            <thead>
                <tr>
                    ${headers.map(header => `<th>${header}</th>`).join('')}
                </tr>
            </thead>
            <tbody>
                ${rows.map(row => `
                    <tr>
                        ${row.map(cell => `<td>${cell}</td>`).join('')}
                    </tr>
                `).join('')}
            </tbody>
        `;
        
        if (summary) {
            this.displaySummary(summary);
        }
    }
    
    /**
     * Display report summary
     */
    displaySummary(summary) {
        const summaryContainer = document.createElement('div');
        summaryContainer.className = 'card mt-4';
        summaryContainer.innerHTML = `
            <div class="card-body">
                <h5 class="card-title">ملخص التقرير</h5>
                ${Object.entries(summary).map(([key, value]) => `
                    <p class="mb-1"><strong>${key}:</strong> ${value}</p>
                `).join('')}
            </div>
        `;
        
        this.reportContainer.appendChild(summaryContainer);
    }
    
    /**
     * Display report filters
     */
    displayFilters(filters) {
        if (!this.reportFilters) return;
        
        this.reportFilters.innerHTML = filters.map(filter => `
            <div class="form-group">
                <label for="${filter.id}">${filter.label}</label>
                <${filter.type === 'select' ? 'select' : 'input'} 
                    id="${filter.id}" 
                    name="${filter.name}" 
                    class="form-control"
                    ${filter.type === 'select' ? '' : `type="${filter.type}"`}
                >
                    ${filter.type === 'select' ? 
                        filter.options.map(option => 
                            `<option value="${option.value}">${option.label}</option>`
                        ).join('') : 
                        ''
                    }
                </${filter.type === 'select' ? 'select' : 'input'}>
            </div>
        `).join('');
    }
    
    /**
     * Display export buttons
     */
    displayExportButtons() {
        if (!this.exportButtons) return;
        
        this.exportButtons.innerHTML = `
            <button class="btn btn-primary" onclick="exportReport('pdf')">
                <i class="fas fa-file-pdf"></i> تصدير PDF
            </button>
            <button class="btn btn-success" onclick="exportReport('excel')">
                <i class="fas fa-file-excel"></i> تصدير Excel
            </button>
            <button class="btn btn-info" onclick="exportReport('csv')">
                <i class="fas fa-file-csv"></i> تصدير CSV
            </button>
        `;
    }
    
    /**
     * Show loading state
     */
    showLoading() {
        if (this.reportContainer) {
            this.reportContainer.innerHTML = `
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
        if (this.reportContainer) {
            this.reportContainer.innerHTML = `
                <div class="alert alert-danger">
                    ${message}
                </div>
            `;
        }
    }
    
    /**
     * Show empty state
     */
    showEmpty(message = 'لا توجد بيانات للعرض') {
        if (this.reportContainer) {
            this.reportContainer.innerHTML = `
                <div class="alert alert-info">
                    ${message}
                </div>
            `;
        }
    }
    
    /**
     * Clear the report
     */
    clear() {
        if (this.reportContainer) {
            this.reportContainer.innerHTML = '';
        }
        if (this.reportTable) {
            this.reportTable.innerHTML = '';
        }
    }
    
    /**
     * Highlight row
     */
    highlightRow(rowIndex) {
        const rows = this.reportTable.querySelectorAll('tbody tr');
        rows.forEach((row, index) => {
            if (index === rowIndex) {
                row.classList.add('table-active');
            } else {
                row.classList.remove('table-active');
            }
        });
    }
    
    /**
     * Get filter values
     */
    getFilterValues() {
        if (!this.reportFilters) return {};
        
        const filters = {};
        const inputs = this.reportFilters.querySelectorAll('input, select');
        
        inputs.forEach(input => {
            filters[input.name] = input.value;
        });
        
        return filters;
    }
}
