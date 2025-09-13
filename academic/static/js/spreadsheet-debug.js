/**
 * Debug version of Academic Spreadsheet class
 */
class AcademicSpreadsheetDebug {
    constructor(config) {
        console.log('=== DEBUG: AcademicSpreadsheet Constructor ===');
        console.log('Config:', config);

        this.endpoint = config.endpoint;
        this.columns = config.columns;
        this.containerSelector = config.container;
        this.modelName = config.modelName;
        this.data = [];
        this.hasUnsavedChanges = false;

        console.log('Endpoint:', this.endpoint);
        console.log('Container:', this.containerSelector);
        console.log('Columns:', this.columns);

        this.init();
    }

    async init() {
        console.log('=== DEBUG: Initialize ===');
        this.showLoadingState();

        // Test 1: Check if container exists
        const container = document.querySelector(this.containerSelector);
        console.log('Container element:', container);
        if (!container) {
            this.showError('Container not found: ' + this.containerSelector);
            return;
        }

        // Test 2: Check if Luckysheet is loaded
        console.log('Luckysheet available:', typeof luckysheet !== 'undefined');
        if (typeof luckysheet === 'undefined') {
            this.showError('Luckysheet library not loaded');
            return;
        }

        // Test 3: Try to load data
        try {
            console.log('=== DEBUG: Loading data ===');
            await this.loadData();
            console.log('Data loaded successfully:', this.data);
        } catch (error) {
            console.error('Failed to load data:', error);
            this.showError('Failed to load data: ' + error.message);
            return;
        }

        // Test 4: Try to initialize Luckysheet
        try {
            console.log('=== DEBUG: Initializing Luckysheet ===');
            this.initLuckysheet();
        } catch (error) {
            console.error('Failed to initialize Luckysheet:', error);
            this.showError('Failed to initialize spreadsheet: ' + error.message);
        }
    }

    async loadData() {
        console.log('Loading data from:', this.endpoint);

        // Check CSRF token
        const csrfToken = this.getCSRFToken();
        console.log('CSRF Token:', csrfToken ? 'Found' : 'Missing');

        try {
            const response = await fetch(this.endpoint, {
                headers: {
                    'X-CSRFToken': csrfToken,
                    'Accept': 'application/json',
                },
                credentials: 'same-origin'
            });

            console.log('Response status:', response.status);
            console.log('Response headers:', [...response.headers.entries()]);

            if (!response.ok) {
                if (response.status === 401) {
                    throw new Error('Authentication required - please log in');
                }
                if (response.status === 403) {
                    throw new Error('Access forbidden - check permissions');
                }
                if (response.status === 404) {
                    throw new Error('API endpoint not found: ' + this.endpoint);
                }
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const responseData = await response.json();
            console.log('Response data:', responseData);

            this.data = responseData.results || responseData || [];
            if (!Array.isArray(this.data)) {
                this.data = [];
            }

            console.log('Final processed data:', this.data);
        } catch (error) {
            console.error('Load data error:', error);
            throw error;
        }
    }

    initLuckysheet() {
        console.log('=== DEBUG: Luckysheet Init ===');

        const container = document.querySelector(this.containerSelector);
        console.log('Container for Luckysheet:', container);

        // Create simple test data
        const sheetData = {
            name: this.modelName,
            index: 0,
            order: 0,
            status: 1,
            celldata: this.createCellData(),
            config: {},
            row: Math.max(this.data.length + 10, 20),
            column: this.columns.length
        };

        console.log('Sheet data for Luckysheet:', sheetData);

        const options = {
            container: this.containerSelector.replace('#', ''),
            showinfobar: false,
            showsheetbar: false,
            showstatisticBar: false,
            showToolbar: true,
            showFormulaBar: true,
            allowEdit: true,
            allowDelete: true,
            allowCopy: true,
            data: [sheetData],
            hook: {
                cellUpdated: (r, c, oldValue, newValue, isRefresh) => {
                    if (!isRefresh && r > 0) {
                        console.log(`Cell updated: [${r},${c}] ${oldValue} -> ${newValue}`);
                        this.hasUnsavedChanges = true;
                        this.updateStatus('Modified');
                    }
                },
                cellEditBefore: (range) => {
                    console.log('Cell edit starting for range:', range);
                    return true; // Allow editing
                },
                cellEditEnd: (text, ri, ci) => {
                    console.log('Cell edit ended:', text, ri, ci);
                }
            }
        };

        console.log('Luckysheet options:', options);

        try {
            luckysheet.create(options);
            console.log('Luckysheet.create() called successfully');

            setTimeout(() => {
                this.hideLoadingState();
                this.updateStatus('Ready');

                // Apply aggressive CSS fixes after initialization
                this.applyPostInitFixes();

                console.log('=== DEBUG: Initialization complete ===');
            }, 1000);

        } catch (error) {
            console.error('Luckysheet.create() error:', error);
            throw error;
        }
    }

    applyPostInitFixes() {
        console.log('=== DEBUG: Applying post-init fixes ===');

        const container = document.querySelector(this.containerSelector);
        if (!container) {
            console.warn('Container not found for post-init fixes');
            return;
        }

        // Force CSS resets on all Luckysheet elements
        this.forceStyleResets();

        // Set up editor positioning monitoring
        this.setupEditorMonitoring();

        // Apply positioning fixes
        this.fixElementPositioning();
    }

    forceStyleResets() {
        console.log('Forcing style resets on Luckysheet elements');

        // Find all elements with luckysheet in the class name
        const luckysheetElements = document.querySelectorAll('[class*="luckysheet"]');

        luckysheetElements.forEach(element => {
            // Reset any conflicting styles
            element.style.fontFamily = 'Arial, sans-serif';
            element.style.fontSize = '';
            element.style.lineHeight = '';
            element.style.margin = '';
            element.style.padding = '';
        });

        // Specific fixes for common problematic elements
        const toolbar = document.querySelector('.luckysheet-wa-editor');
        if (toolbar) {
            toolbar.style.position = 'absolute';
            toolbar.style.zIndex = '10001';
        }

        const formulaBar = document.querySelector('.luckysheet-wa-calculate');
        if (formulaBar) {
            formulaBar.style.position = 'absolute';
            formulaBar.style.zIndex = '10001';
        }
    }

    setupEditorMonitoring() {
        console.log('Setting up editor position monitoring');

        const container = document.querySelector(this.containerSelector);

        // Monitor for cell clicks
        if (container) {
            container.addEventListener('mousedown', (event) => {
                console.log('Cell clicked, monitoring editor...');

                // Check editor position after a brief delay
                setTimeout(() => {
                    this.checkAndFixEditorPosition();
                }, 50);
            });
        }
    }

    fixElementPositioning() {
        console.log('Applying element positioning fixes');

        // Get the container bounds
        const container = document.querySelector(this.containerSelector);
        if (!container) return;

        const containerRect = container.getBoundingClientRect();
        console.log('Container bounds:', containerRect);

        // Ensure all Luckysheet elements are positioned relative to container
        const positionedElements = document.querySelectorAll('[class*="luckysheet"][style*="position"]');
        positionedElements.forEach(element => {
            const rect = element.getBoundingClientRect();

            // If element is far outside the container, reposition it
            if (rect.top > containerRect.bottom + 100 || rect.left > containerRect.right + 100) {
                console.log('Repositioning misplaced element:', element);
                element.style.top = '0px';
                element.style.left = '0px';
            }
        });
    }

    checkAndFixEditorPosition() {
        const editor = document.querySelector('.luckysheet-wa-editor');
        const container = document.querySelector(this.containerSelector);

        if (!editor || !container) return;

        const editorRect = editor.getBoundingClientRect();
        const containerRect = container.getBoundingClientRect();

        console.log('Editor position:', editorRect);
        console.log('Container position:', containerRect);

        // If editor is outside the visible area or container, fix it
        if (editorRect.top > window.innerHeight ||
            editorRect.left > window.innerWidth ||
            editorRect.top < containerRect.top - 50 ||
            editorRect.left < containerRect.left - 50) {

            console.log('Fixing mispositioned editor');

            // Position editor within the container
            const newTop = containerRect.top + window.scrollY + 50;
            const newLeft = containerRect.left + window.scrollX + 50;

            editor.style.position = 'absolute';
            editor.style.top = newTop + 'px';
            editor.style.left = newLeft + 'px';
            editor.style.zIndex = '10001';
        }
    }

    createCellData() {
        const cellData = [];

        // Headers
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

        // Data rows
        this.data.forEach((row, rowIndex) => {
            this.columns.forEach((col, colIndex) => {
                const value = row[col.data];
                if (value !== null && value !== undefined && value !== '') {
                    cellData.push({
                        r: rowIndex + 1,
                        c: colIndex,
                        v: {
                            v: String(value),
                            ct: { t: 's' }
                        }
                    });
                }
            });
        });

        console.log('Created cell data:', cellData.slice(0, 10)); // Show first 10 items
        return cellData;
    }

    getCSRFToken() {
        const tokenElement = document.querySelector('[name=csrfmiddlewaretoken]');
        return tokenElement ? tokenElement.value : '';
    }

    updateStatus(message) {
        console.log('Status:', message);
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
            'Error': 'bg-danger'
        };
        return colors[status] || 'bg-secondary';
    }

    showLoadingState() {
        console.log('Showing loading state');
        const overlay = document.getElementById('loading-overlay');
        if (overlay) overlay.style.display = 'flex';
    }

    hideLoadingState() {
        console.log('Hiding loading state');
        const overlay = document.getElementById('loading-overlay');
        if (overlay) overlay.style.display = 'none';
    }

    showError(message) {
        console.error('ERROR:', message);
        this.hideLoadingState();
        this.updateStatus('Error');

        const alert = document.createElement('div');
        alert.className = 'alert alert-danger alert-dismissible fade show';
        alert.innerHTML = `
            <h6><i class="fas fa-exclamation-triangle me-2"></i>Debug Error</h6>
            <p class="mb-2">${message}</p>
            <p class="small mb-0">Check browser console for detailed debug information.</p>
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

        const container = document.querySelector('.container-fluid');
        if (container) {
            container.insertBefore(alert, container.firstChild);
        }
    }
}

// Export for global access
window.AcademicSpreadsheetDebug = AcademicSpreadsheetDebug;