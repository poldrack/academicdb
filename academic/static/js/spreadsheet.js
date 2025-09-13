/**
 * Academic Spreadsheet class using Luckysheet
 * Provides Excel-like functionality for managing academic data
 */
class AcademicSpreadsheet {
    constructor(config) {
        this.endpoint = config.endpoint;
        this.columns = config.columns;
        this.containerSelector = config.container;
        this.modelName = config.modelName;
        this.luckysheet = null;
        this.data = [];
        this.saveTimeout = null;
        this.isLoading = false;
        this.hasUnsavedChanges = false;

        // Configuration
        this.autoSaveDelay = 2000; // 2 seconds
        this.enableAutoSave = config.autoSave !== false;

        console.log('Initializing AcademicSpreadsheet with config:', config);
        this.init();
    }

    async init() {
        try {
            console.log('Starting spreadsheet initialization...');
            this.showLoadingState();

            // Wait for DOM to be ready
            if (document.readyState !== 'complete') {
                await new Promise(resolve => {
                    window.addEventListener('load', resolve);
                });
            }

            // Load data from API
            await this.loadData();

            // Initialize Luckysheet with a small delay to ensure DOM is ready
            setTimeout(() => {
                this.initializeLuckysheet();
            }, 100);

        } catch (error) {
            console.error('Failed to initialize spreadsheet:', error);
            this.hideLoadingState();
            this.showError('Failed to load spreadsheet data: ' + error.message);
        }
    }

    async loadData() {
        console.log('Loading data from:', this.endpoint);
        try {
            const response = await fetch(this.endpoint, {
                headers: {
                    'X-CSRFToken': this.getCSRFToken(),
                    'Accept': 'application/json',
                },
                credentials: 'same-origin'
            });

            if (!response.ok) {
                if (response.status === 401) {
                    window.location.href = '/accounts/login/';
                    return;
                }
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const responseData = await response.json();
            this.data = responseData.results || responseData || [];

            // Ensure data is an array
            if (!Array.isArray(this.data)) {
                this.data = [];
            }

            console.log('Loaded data:', this.data);

        } catch (error) {
            console.error('Failed to load data:', error);
            throw error;
        }
    }

    initializeLuckysheet() {
        console.log('Initializing Luckysheet...');

        // Check if Luckysheet is loaded
        if (typeof luckysheet === 'undefined') {
            console.error('Luckysheet library not loaded');
            this.hideLoadingState();
            this.showError('Spreadsheet library failed to load. Please refresh the page.');
            return;
        }

        const container = document.querySelector(this.containerSelector);
        if (!container) {
            console.error(`Container not found: ${this.containerSelector}`);
            this.hideLoadingState();
            this.showError('Spreadsheet container not found');
            return;
        }

        console.log('Container found:', container);

        // Prepare simple sheet data
        const sheetData = this.prepareSimpleSheetData();
        console.log('Sheet data prepared:', sheetData);

        try {
            // Simple Luckysheet configuration
            const options = {
                container: this.containerSelector.replace('#', ''),
                showinfobar: false,
                showsheetbar: false,
                showstatisticBar: false,
                enableAddRow: true,
                enableAddCol: false,
                allowCopy: true,
                allowEdit: true,
                allowDelete: true,
                data: [sheetData],
                hook: {
                    cellUpdated: (r, c, oldValue, newValue, isRefresh) => {
                        if (!isRefresh && r > 0) { // Skip header row
                            console.log(`Cell updated: [${r},${c}] ${oldValue} -> ${newValue}`);
                            this.handleCellChange(r, c, newValue);
                        }
                    }
                }
            };

            console.log('Luckysheet options:', options);

            // Initialize Luckysheet
            luckysheet.create(options);

            // Setup event handlers after a delay
            setTimeout(() => {
                this.setupEventHandlers();
                this.hideLoadingState();
                this.updateStatus('Ready');
                console.log('Luckysheet initialized successfully');
            }, 1000);

        } catch (error) {
            console.error('Error initializing Luckysheet:', error);
            this.hideLoadingState();
            this.showError('Failed to initialize spreadsheet: ' + error.message);
        }
    }

    prepareSimpleSheetData() {
        console.log('Preparing simple sheet data...');

        // Create basic spreadsheet data structure
        const cellData = [];

        // Add headers
        this.columns.forEach((col, colIndex) => {
            cellData.push({
                r: 0,
                c: colIndex,
                v: {
                    v: col.title || col.data,
                    ct: { t: 's' },
                    bg: '#f0f0f0',
                    bl: 1
                }
            });
        });

        // Add data rows
        this.data.forEach((row, rowIndex) => {
            this.columns.forEach((col, colIndex) => {
                const value = row[col.data];
                if (value !== null && value !== undefined && value !== '') {
                    cellData.push({
                        r: rowIndex + 1,
                        c: colIndex,
                        v: {
                            v: this.formatCellValue(value, col.type),
                            ct: { t: this.getCellType(col.type) }
                        }
                    });
                }
            });
        });

        return {
            name: this.modelName,
            index: 0,
            order: 0,
            status: 1,
            celldata: cellData,
            config: {},
            row: Math.max(this.data.length + 10, 20),
            column: this.columns.length
        };
    }

    convertToLuckysheetData() {
        console.log('Converting data for Luckysheet...');

        const rows = [];

        // Header row
        const headerRow = this.columns.map(col => ({
            ct: { t: 's' }, // string type
            v: col.title || col.data,
            bg: '#f0f0f0',
            bl: 1 // bold
        }));
        rows.push(headerRow);

        // Data rows
        if (Array.isArray(this.data)) {
            this.data.forEach((row, rowIndex) => {
                const dataRow = this.columns.map((col) => {
                    const value = row[col.data];
                    return {
                        ct: { t: this.getCellType(col.type) },
                        v: this.formatCellValue(value, col.type)
                    };
                });
                rows.push(dataRow);
            });
        }

        // Add empty rows for editing
        const minRows = Math.max(this.data.length + 10, 20);
        while (rows.length < minRows) {
            const emptyRow = this.columns.map(() => ({
                ct: { t: 's' },
                v: ''
            }));
            rows.push(emptyRow);
        }

        // Prepare column configuration
        const colConfig = {};
        this.columns.forEach((col, index) => {
            colConfig[index] = {
                width: this.getColumnWidth(col.data, col.type)
            };
        });

        return {
            name: this.modelName,
            celldata: this.convertRowsToLuckysheetCelldata(rows),
            config: {
                merge: {},
                rowlen: colConfig,
                columnlen: colConfig
            },
            row: rows.length,
            column: this.columns.length
        };
    }

    convertRowsToLuckysheetCelldata(rows) {
        const celldata = [];

        rows.forEach((row, r) => {
            row.forEach((cell, c) => {
                if (cell.v !== '') {
                    celldata.push({
                        r: r,
                        c: c,
                        v: cell
                    });
                }
            });
        });

        return celldata;
    }

    getCellType(type) {
        const typeMapping = {
            'numeric': 'n',
            'number': 'n',
            'boolean': 'b',
            'checkbox': 'b',
            'date': 'd',
            'datetime': 'd',
            'text': 's',
            'string': 's'
        };
        return typeMapping[type] || 's';
    }

    formatCellValue(value, type) {
        if (value === null || value === undefined) return '';

        switch (type) {
            case 'boolean':
            case 'checkbox':
                return value ? 'Yes' : 'No';
            case 'date':
            case 'datetime':
                return value ? new Date(value).toLocaleDateString() : '';
            default:
                return String(value);
        }
    }

    getColumnWidth(fieldName, type) {
        const widths = {
            'name': 250,
            'title': 300,
            'place': 200,
            'location': 200,
            'institution': 200,
            'conference_name': 200,
            'authors': 250,
            'year': 80,
            'month': 100,
            'semester': 100,
            'course_number': 120,
            'enrollment': 100,
            'level': 120,
            'presentation_type': 140,
            'link': 200,
            'invited': 80,
            'virtual': 80,
            'date': 120
        };

        return widths[fieldName] || (type === 'checkbox' ? 80 : 150);
    }

    setupEventHandlers() {
        // Save button
        const saveBtn = document.getElementById('save-btn');
        if (saveBtn) {
            saveBtn.addEventListener('click', () => this.saveChanges());
        }

        // Add row button
        const addRowBtn = document.getElementById('add-row-btn');
        if (addRowBtn) {
            addRowBtn.addEventListener('click', () => this.addRow());
        }

        // Import button
        const importBtn = document.getElementById('import-btn');
        const fileInput = document.getElementById('csv-file-input');
        if (importBtn && fileInput) {
            importBtn.addEventListener('click', () => fileInput.click());
            fileInput.addEventListener('change', (e) => this.handleFileImport(e));
        }

        // Export button
        const exportBtn = document.getElementById('export-btn');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => this.exportExcel());
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', (event) => {
            if (event.ctrlKey && event.key === 's') {
                event.preventDefault();
                this.saveChanges();
                return false;
            }
        });
    }

    handleCellChange(row, col, value) {
        console.log(`Cell changed: [${row},${col}] = "${value}"`);

        // Skip header row
        if (row === 0) return;

        this.hasUnsavedChanges = true;
        this.updateStatus('Modified');

        if (this.enableAutoSave) {
            this.scheduleAutoSave();
        }
    }

    scheduleAutoSave() {
        if (this.saveTimeout) {
            clearTimeout(this.saveTimeout);
        }

        this.saveTimeout = setTimeout(() => {
            this.saveChanges();
        }, this.autoSaveDelay);
    }

    async saveChanges() {
        if (!this.hasUnsavedChanges || this.isLoading) {
            return;
        }

        this.isLoading = true;
        this.updateStatus('Saving...');

        try {
            const currentData = this.getSpreadsheetData();
            const updates = this.prepareUpdates(currentData);

            if (updates.length > 0) {
                await this.bulkUpdate(updates);
            }

            this.hasUnsavedChanges = false;
            this.updateStatus('Saved');

            setTimeout(() => {
                if (!this.hasUnsavedChanges) {
                    this.updateStatus('Ready');
                }
            }, 2000);

        } catch (error) {
            console.error('Save failed:', error);
            this.updateStatus('Error');
            this.showError('Failed to save changes: ' + error.message);
        } finally {
            this.isLoading = false;
        }
    }

    getSpreadsheetData() {
        if (!luckysheet || !luckysheet.getSheetData) {
            console.warn('Luckysheet not available for data extraction');
            return [];
        }

        try {
            const sheetData = luckysheet.getSheetData();
            const rows = [];

            // Skip header row (index 0)
            for (let r = 1; r < sheetData.length; r++) {
                if (sheetData[r]) {
                    const row = [];
                    for (let c = 0; c < this.columns.length; c++) {
                        const cell = sheetData[r][c];
                        row.push(cell && cell.v !== undefined ? cell.v : '');
                    }
                    rows.push(row);
                }
            }

            return rows;
        } catch (error) {
            console.error('Error getting spreadsheet data:', error);
            return [];
        }
    }

    prepareUpdates(currentData) {
        const updates = [];

        for (let i = 0; i < currentData.length; i++) {
            const rowData = currentData[i];
            const originalRow = this.data[i];

            // Skip empty rows
            if (this.isEmptyRow(rowData)) {
                continue;
            }

            // Convert array data back to object
            const rowObject = {};
            this.columns.forEach((col, index) => {
                if (index < rowData.length) {
                    rowObject[col.data] = this.parseFieldValue(rowData[index], col.type);
                }
            });

            // Add ID if updating existing row
            if (originalRow && originalRow.id) {
                rowObject.id = originalRow.id;
            }

            updates.push(rowObject);
        }

        return updates;
    }

    parseFieldValue(value, type) {
        if (value === '' || value === null || value === undefined) {
            return null;
        }

        switch (type) {
            case 'numeric':
            case 'number':
                const num = parseFloat(value);
                return isNaN(num) ? null : num;
            case 'boolean':
            case 'checkbox':
                return value === 'Yes' || value === true || value === 'true' || value === 1;
            case 'date':
            case 'datetime':
                try {
                    const date = new Date(value);
                    return isNaN(date.getTime()) ? null : date.toISOString().split('T')[0];
                } catch {
                    return null;
                }
            default:
                return String(value).trim();
        }
    }

    isEmptyRow(rowData) {
        return rowData.every(cell =>
            cell === null ||
            cell === undefined ||
            cell === '' ||
            (typeof cell === 'string' && cell.trim() === '')
        );
    }

    async bulkUpdate(data) {
        const response = await fetch(`${this.endpoint}bulk_update/`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken(),
            },
            credentials: 'same-origin',
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
        }

        const result = await response.json();

        if (result.errors && result.errors.length > 0) {
            console.warn('Some updates failed:', result.errors);
            this.showError(`${result.errors.length} updates failed. Check console for details.`);
        }

        return result;
    }

    addRow() {
        try {
            if (luckysheet && luckysheet.insertRow) {
                luckysheet.insertRow();
            } else {
                console.warn('Insert row function not available');
            }
        } catch (error) {
            console.error('Failed to add row:', error);
            this.showError('Failed to add row');
        }
    }

    async handleFileImport(event) {
        const file = event.target.files[0];
        if (!file) return;

        if (!file.name.toLowerCase().endsWith('.csv')) {
            this.showError('Please select a CSV file');
            return;
        }

        this.updateStatus('Importing...');

        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch(`${this.endpoint}import_csv/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': this.getCSRFToken(),
                },
                credentials: 'same-origin',
                body: formData
            });

            if (!response.ok) {
                throw new Error(`Import failed: ${response.statusText}`);
            }

            const result = await response.json();

            if (result.success) {
                this.updateStatus('Import successful');
                setTimeout(() => window.location.reload(), 1000);
            } else {
                throw new Error(result.error || 'Import failed');
            }

        } catch (error) {
            console.error('Import failed:', error);
            this.showError('Import failed: ' + error.message);
            this.updateStatus('Ready');
        }

        // Reset file input
        event.target.value = '';
    }

    async exportExcel() {
        try {
            const response = await fetch(`${this.endpoint}export_excel/`, {
                headers: {
                    'X-CSRFToken': this.getCSRFToken(),
                },
                credentials: 'same-origin'
            });

            if (!response.ok) {
                throw new Error('Export failed');
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;

            const contentDisposition = response.headers.get('content-disposition');
            let filename = `${this.modelName.toLowerCase()}_export.xlsx`;
            if (contentDisposition) {
                const matches = contentDisposition.match(/filename="?([^"]*)"?/);
                if (matches && matches[1]) {
                    filename = matches[1];
                }
            }

            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

        } catch (error) {
            console.error('Export failed:', error);
            this.showError('Failed to export data: ' + error.message);
        }
    }

    getCSRFToken() {
        const tokenElement = document.querySelector('[name=csrfmiddlewaretoken]');
        return tokenElement ? tokenElement.value : '';
    }

    updateStatus(message) {
        const statusText = document.getElementById('status-text');
        const statusBadge = document.getElementById('status-badge');

        if (statusText) statusText.textContent = message;
        if (statusBadge) {
            statusBadge.textContent = message;
            statusBadge.className = `badge ${this.getStatusColor(message)}`;
        }
    }

    getStatusColor(status) {
        const colors = {
            'Ready': 'bg-secondary',
            'Modified': 'bg-warning text-dark',
            'Saving...': 'bg-primary',
            'Saved': 'bg-success',
            'Error': 'bg-danger',
            'Importing...': 'bg-info',
            'Import successful': 'bg-success'
        };
        return colors[status] || 'bg-secondary';
    }

    showLoadingState() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) overlay.style.display = 'flex';
    }

    hideLoadingState() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) overlay.style.display = 'none';
    }

    showError(message) {
        const alert = document.createElement('div');
        alert.className = 'alert alert-danger alert-dismissible fade show';
        alert.innerHTML = `
            <i class="fas fa-exclamation-triangle me-2"></i>${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

        const container = document.querySelector('.container-fluid');
        if (container) {
            container.insertBefore(alert, container.firstChild);

            setTimeout(() => {
                if (alert.parentNode) {
                    alert.remove();
                }
            }, 8000);
        }
    }

    destroy() {
        if (luckysheet && luckysheet.destroy) {
            luckysheet.destroy();
        }

        if (this.saveTimeout) {
            clearTimeout(this.saveTimeout);
        }
    }
}

// Export for global access
window.AcademicSpreadsheet = AcademicSpreadsheet;