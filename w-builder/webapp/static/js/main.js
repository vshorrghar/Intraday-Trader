// Wealth Manager Pro - Modern Frontend

let uploadedFiles = {
    holdings: null,
    pnl: null
};

let analysisResults = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initializeDragDrop();
    initializeFileInput();
    scanDownloads();
});

// ==================== DRAG & DROP ====================

function initializeDragDrop() {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');

    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        handleFiles(e.dataTransfer.files);
    });
}

function initializeFileInput() {
    const fileInput = document.getElementById('fileInput');
    fileInput.addEventListener('change', (e) => {
        handleFiles(e.target.files);
    });
}

function handleFiles(files) {
    for (let file of files) {
        if (file.name.endsWith('.xlsx') || file.name.endsWith('.xls')) {
            uploadFile(file);
        } else {
            showError('Invalid file: ' + file.name + '. Only Excel files (.xlsx, .xls) are allowed.');
        }
    }
}

async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    try {
        showNotification('Uploading ' + file.name + '...', 'info');

        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (result.success) {
            showNotification('✓ ' + file.name + ' uploaded', 'success');
            addUploadedFile(result);

            // Store path
            if (result.type === 'holdings') {
                uploadedFiles.holdings = result.path;
            } else if (result.type === 'pnl') {
                uploadedFiles.pnl = result.path;
            }
        } else {
            showError('Upload failed: ' + result.error);
        }
    } catch (error) {
        showError('Upload error: ' + error.message);
    }
}

function addUploadedFile(fileInfo) {
    const container = document.getElementById('uploadedFiles');
    const card = createFileCard(fileInfo);
    container.appendChild(card);
}

// ==================== SCAN DOWNLOADS ====================

async function scanDownloads() {
    try {
        const response = await fetch('/api/downloads/scan');
        const result = await response.json();

        if (result.success && result.files.length > 0) {
            displayScannedFiles(result.files);
        }
    } catch (error) {
        console.error('Scan failed:', error);
    }
}

function displayScannedFiles(files) {
    const container = document.getElementById('scannedFiles');
    container.innerHTML = '<div style="padding: 0 30px;"><h4 style="margin: 20px 0 10px 0;"><i class="fas fa-folder-open"></i> Files from Downloads</h4></div>';

    // Group by type and show latest
    const types = ['holdings', 'pnl'];
    types.forEach(type => {
        const fileOfType = files.find(f => f.type === type);
        if (fileOfType) {
            const card = createFileCard(fileOfType);
            container.appendChild(card);

            // Auto-select
            if (!uploadedFiles[type]) {
                uploadedFiles[type] = fileOfType.path;
            }
        }
    });
}

function createFileCard(fileInfo) {
    const div = document.createElement('div');
    div.className = 'file-card';

    const isOld = fileInfo.age_days > 3;
    const typeColors = {
        holdings: 'background: #dbeafe; color: #1e40af;',
        pnl: 'background: #d1fae5; color: #065f46;',
        mutual_funds: 'background: #e9d5ff; color: #6b21a8;'
    };

    div.innerHTML = `
        <div class="file-info">
            <i class="fas fa-file-excel file-icon"></i>
            <div>
                <div style="font-weight: 600; color: #1e293b;">${fileInfo.name}</div>
                <div style="font-size: 0.9rem; color: #64748b;">
                    ${(fileInfo.size / 1024).toFixed(1)} KB
                    ${isOld ? '<span style="color: #ef4444; font-weight: 600; margin-left: 10px;">⚠️ ' + fileInfo.age_days + ' days old</span>' : ''}
                </div>
            </div>
        </div>
        <span class="badge-custom" style="${typeColors[fileInfo.type] || 'background: #e2e8f0; color: #475569;'}">
            ${formatFileType(fileInfo.type)}
        </span>
    `;

    return div;
}

function formatFileType(type) {
    const names = {
        holdings: 'Holdings',
        pnl: 'P&L Report',
        mutual_funds: 'Mutual Funds'
    };
    return names[type] || 'Unknown';
}

// ==================== RUN ANALYSIS ====================

async function runAnalysis() {
    if (!uploadedFiles.holdings) {
        showError('Please upload or select a Holdings file first!');
        return;
    }

    const btn = document.getElementById('analyzeBtn');
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner"></div> Analyzing...';

    document.getElementById('progressSection').classList.remove('hidden');
    document.getElementById('errorDisplay').classList.add('hidden');

    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                holdings_file: uploadedFiles.holdings,
                pnl_file: uploadedFiles.pnl
            })
        });

        const result = await response.json();

        if (result.success) {
            analysisResults = result.results;
            displayResults(result.results);
            showNotification('✓ Analysis complete!', 'success');
        } else {
            showError('Analysis failed: ' + (result.error || 'Unknown error'));
        }
    } catch (error) {
        showError('Analysis error: ' + error.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-play"></i> Run Analysis';
        document.getElementById('progressSection').classList.add('hidden');
    }

    pollAnalysisStatus();
}

async function pollAnalysisStatus() {
    const interval = setInterval(async () => {
        try {
            const response = await fetch('/api/status');
            const status = await response.json();

            document.getElementById('progressBar').style.width = status.progress + '%';
            document.getElementById('progressPercent').textContent = status.progress + '%';
            document.getElementById('progressMessage').textContent = status.message;

            if (status.status === 'completed' || status.status === 'error') {
                clearInterval(interval);
                if (status.status === 'completed' && status.results) {
                    analysisResults = status.results;
                    displayResults(status.results);
                } else if (status.status === 'error') {
                    showError('Analysis failed: ' + status.error);
                }
            }
        } catch (error) {
            clearInterval(interval);
        }
    }, 1000);
}

// ==================== DISPLAY RESULTS ====================

function displayResults(results) {
    document.getElementById('emptyState').classList.add('hidden');

    const overviewContent = document.getElementById('overviewContent');
    overviewContent.classList.remove('hidden');

    const summary = results.portfolio_summary;
    const market = results.market_context;

    overviewContent.innerHTML = `
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Total Value</div>
                <div class="stat-value">${formatCurrency(summary.total_value)}</div>
            </div>
            <div class="stat-card success">
                <div class="stat-label">Unrealized P&L</div>
                <div class="stat-value">${formatCurrency(summary.unrealized_pnl)}</div>
            </div>
            <div class="stat-card warning">
                <div class="stat-label">Total Holdings</div>
                <div class="stat-value">${summary.total_holdings}</div>
            </div>
            <div class="stat-card danger">
                <div class="stat-label">AWS Cost (MTD)</div>
                <div class="stat-value">$${results.aws_costs.month_to_date.toFixed(2)}</div>
            </div>
        </div>

        <div style="background: #f8fafc; padding: 25px; border-radius: 15px; margin-bottom: 30px;">
            <h4 style="margin-bottom: 20px;"><i class="fas fa-globe"></i> Market Context</h4>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px;">
                <div>
                    <div style="color: #64748b; font-size: 0.9rem;">FII Flow</div>
                    <div style="font-size: 1.5rem; font-weight: 700; color: ${market.fii_net_crores >= 0 ? '#10b981' : '#ef4444'};">
                        ₹${market.fii_net_crores.toFixed(2)} Cr
                    </div>
                </div>
                <div>
                    <div style="color: #64748b; font-size: 0.9rem;">DII Flow</div>
                    <div style="font-size: 1.5rem; font-weight: 700; color: ${market.dii_net_crores >= 0 ? '#10b981' : '#ef4444'};">
                        ₹${market.dii_net_crores.toFixed(2)} Cr
                    </div>
                </div>
                <div>
                    <div style="color: #64748b; font-size: 0.9rem;">Nifty 50</div>
                    <div style="font-size: 1.5rem; font-weight: 700; color: ${(market.indices_change['NIFTY 50'] || 0) >= 0 ? '#10b981' : '#ef4444'};">
                        ${(market.indices_change['NIFTY 50'] || 0).toFixed(2)}%
                    </div>
                </div>
            </div>
        </div>
    `;

    // Render other tabs
    renderIntradayTab(results.intraday_setups);
    renderMultibaggerTab(results.multibaggers);
    renderBrutalTab(results.brutal_assessments);
    renderActionsTab(results.portfolio_actions);
    renderCostsTab(results.aws_costs);
}

function renderIntradayTab(setups) {
    const container = document.getElementById('intraday-tab');
    if (!setups || setups.length === 0) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-bolt"></i><h3>No intraday setups</h3></div>';
        return;
    }

    let html = '<h3 style="margin-bottom: 25px;"><i class="fas fa-bolt"></i> Today\'s 10 Intraday Picks</h3>';

    setups.forEach((setup, i) => {
        const risk = setup.entry_price - setup.stop_loss;
        const reward = setup.target_price - setup.entry_price;
        const rr = risk > 0 ? (reward / risk).toFixed(2) : 'N/A';

        html += `
            <div class="analysis-card">
                <div style="display: flex; justify-between; align-items: start; margin-bottom: 15px;">
                    <h4 style="margin: 0;">${i + 1}. ${setup.stock_name}</h4>
                    <span class="badge-custom" style="background: #fef3c7; color: #92400e;">RR: 1:${rr}</span>
                </div>
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 15px;">
                    <div>
                        <div style="color: #64748b; font-size: 0.85rem;">Entry</div>
                        <div style="font-size: 1.2rem; font-weight: 600; color: #3b82f6;">₹${setup.entry_price.toFixed(2)}</div>
                    </div>
                    <div>
                        <div style="color: #64748b; font-size: 0.85rem;">Target</div>
                        <div style="font-size: 1.2rem; font-weight: 600; color: #10b981;">₹${setup.target_price.toFixed(2)}</div>
                    </div>
                    <div>
                        <div style="color: #64748b; font-size: 0.85rem;">Stop Loss</div>
                        <div style="font-size: 1.2rem; font-weight: 600; color: #ef4444;">₹${setup.stop_loss.toFixed(2)}</div>
                    </div>
                </div>
                <p style="margin: 0; color: #475569;">${setup.rationale}</p>
            </div>
        `;
    });

    container.innerHTML = html;
}

function renderMultibaggerTab(multibaggers) {
    const container = document.getElementById('multibagger-tab');
    if (!multibaggers || multibaggers.length === 0) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-gem"></i><h3>No multibaggers found</h3></div>';
        return;
    }

    let html = '<h3 style="margin-bottom: 25px;"><i class="fas fa-gem"></i> Multibagger Opportunities</h3>';

    multibaggers.forEach((mb, i) => {
        html += `
            <div class="analysis-card">
                <div style="display: flex; justify-between; align-items: start; margin-bottom: 15px;">
                    <div>
                        <h4 style="margin: 0 0 10px 0;">${i + 1}. ${mb.stock_name} (${mb.symbol})</h4>
                        <span class="badge-custom" style="background: #e9d5ff; color: #6b21a8;">${mb.category.toUpperCase()}</span>
                        <span class="badge-custom" style="background: #d1fae5; color: #065f46; margin-left: 10px;">Score: ${mb.multibagger_score}/10</span>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 15px;">
                    <div>
                        <div style="color: #64748b; font-size: 0.85rem;">Current</div>
                        <div style="font-size: 1.2rem; font-weight: 600;">₹${mb.current_price.toFixed(2)}</div>
                    </div>
                    <div>
                        <div style="color: #64748b; font-size: 0.85rem;">3Y Target</div>
                        <div style="font-size: 1.2rem; font-weight: 600; color: #10b981;">₹${mb.estimated_target_3yr.toFixed(2)}</div>
                    </div>
                    <div>
                        <div style="color: #64748b; font-size: 0.85rem;">Upside</div>
                        <div style="font-size: 1.2rem; font-weight: 600; color: #3b82f6;">+${mb.upside_potential_pct.toFixed(1)}%</div>
                    </div>
                </div>
                <p style="margin-bottom: 10px; color: #475569;">${mb.rationale}</p>
                <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #e2e8f0;">
                    <div style="font-weight: 600; margin-bottom: 5px;">Growth Drivers:</div>
                    <ul style="margin: 0; padding-left: 20px;">
                        ${mb.growth_drivers.map(d => `<li>${d}</li>`).join('')}
                    </ul>
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
}

function renderBrutalTab(assessments) {
    const container = document.getElementById('brutal-tab');
    if (!assessments || assessments.length === 0) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-fire"></i><h3>No assessments</h3></div>';
        return;
    }

    let html = '<h3 style="margin-bottom: 25px;"><i class="fas fa-fire"></i> Brutal Portfolio Assessment</h3>';

    assessments.forEach(a => {
        const colors = {
            QUALITY: { bg: '#d1fae5', border: '#10b981', text: '#065f46' },
            DECENT: { bg: '#dbeafe', border: '#3b82f6', text: '#1e40af' },
            MEDIOCRE: { bg: '#fef3c7', border: '#f59e0b', text: '#92400e' },
            WEAK: { bg: '#fed7aa', border: '#f97316', text: '#9a3412' },
            JUNK: { bg: '#fee2e2', border: '#ef4444', text: '#991b1b' }
        };
        const color = colors[a.verdict] || colors.MEDIOCRE;

        html += `
            <div class="analysis-card" style="border-left: 4px solid ${color.border}; background: ${color.bg};">
                <div style="display: flex; justify-between; margin-bottom: 15px;">
                    <div>
                        <h4 style="margin: 0 0 10px 0;">${a.name}</h4>
                        <span class="badge-custom" style="background: white; color: ${color.text};">${a.verdict}</span>
                        <span class="badge-custom" style="background: white; color: ${color.text}; margin-left: 10px;">Score: ${a.quality_score}/10</span>
                        ${a.is_penny_position ? '<span class="badge-custom" style="background: #e9d5ff; color: #6b21a8; margin-left: 10px;">💸 PENNY</span>' : ''}
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 1.3rem; font-weight: 700;">₹${a.position_value.toFixed(0)}</div>
                        <div style="font-size: 0.85rem; color: #64748b;">@ ₹${a.current_price.toFixed(2)}</div>
                    </div>
                </div>
                <div style="font-weight: 600; margin-bottom: 10px;">Action: ${a.action_recommendation}</div>
                <div style="background: rgba(255,255,255,0.5); padding: 15px; border-radius: 8px;">
                    <div style="font-weight: 600; margin-bottom: 5px;">Brutal Truth:</div>
                    <p style="margin: 0;">${a.brutal_truth}</p>
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
}

function renderActionsTab(actions) {
    const container = document.getElementById('actions-tab');
    if (!actions || actions.length === 0) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-tasks"></i><h3>No actions</h3></div>';
        return;
    }

    let html = '<h3 style="margin-bottom: 25px;"><i class="fas fa-tasks"></i> Portfolio Actions</h3>';

    actions.forEach(a => {
        const priorityColors = {
            HIGH: { bg: '#fee2e2', text: '#991b1b' },
            MEDIUM: { bg: '#fef3c7', text: '#92400e' },
            LOW: { bg: '#d1fae5', text: '#065f46' }
        };
        const pColor = priorityColors[a.priority] || priorityColors.MEDIUM;

        html += `
            <div class="analysis-card">
                <div style="display: flex; justify-between; margin-bottom: 15px;">
                    <div>
                        <h4 style="margin: 0 0 10px 0;">${a.name}</h4>
                        <span class="badge-custom" style="background: ${pColor.bg}; color: ${pColor.text};">${a.priority}</span>
                        <span class="badge-custom" style="background: #dbeafe; color: #1e40af; margin-left: 10px;">${a.action}</span>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 1.3rem; font-weight: 700; color: ${a.current_pnl_pct >= 0 ? '#10b981' : '#ef4444'};">
                            ${a.current_pnl_pct >= 0 ? '+' : ''}${a.current_pnl_pct.toFixed(2)}%
                        </div>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 15px;">
                    <div>
                        <div style="font-size: 0.8rem; color: #64748b;">Current</div>
                        <div style="font-weight: 600;">₹${a.current_price.toFixed(2)}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.8rem; color: #64748b;">Avg Cost</div>
                        <div style="font-weight: 600;">₹${a.avg_cost.toFixed(2)}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.8rem; color: #64748b;">Target</div>
                        <div style="font-weight: 600; color: #10b981;">₹${a.target_price.toFixed(2)}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.8rem; color: #64748b;">Stop</div>
                        <div style="font-weight: 600; color: #ef4444;">₹${a.stop_loss.toFixed(2)}</div>
                    </div>
                </div>
                ${a.quantity_suggestion > 0 ? `<div style="background: #dbeafe; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
                    <strong>Suggested Quantity:</strong> ${a.quantity_suggestion} shares
                </div>` : ''}
                <p style="margin: 0; color: #475569;">${a.rationale}</p>
            </div>
        `;
    });

    container.innerHTML = html;
}

function renderCostsTab(costs) {
    const container = document.getElementById('costs-tab');
    container.innerHTML = `
        <h3 style="margin-bottom: 25px;"><i class="fas fa-dollar-sign"></i> AWS Cost Monitor</h3>
        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; margin-bottom: 30px;">
            <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 30px; border-radius: 15px;">
                <div style="opacity: 0.9; margin-bottom: 10px;">Month-to-Date</div>
                <div style="font-size: 2.5rem; font-weight: 700;">$${costs.month_to_date.toFixed(2)}</div>
            </div>
            <div style="background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); color: white; padding: 30px; border-radius: 15px;">
                <div style="opacity: 0.9; margin-bottom: 10px;">Forecast Month-End</div>
                <div style="font-size: 2.5rem; font-weight: 700;">$${costs.forecast_month_end.toFixed(2)}</div>
            </div>
        </div>
        <h4 style="margin-bottom: 15px;">Costs by Service</h4>
        ${Object.entries(costs.service_costs || {}).map(([svc, cost]) => `
            <div class="analysis-card" style="display: flex; justify-between; align-items: center;">
                <span style="font-weight: 600;">${svc}</span>
                <span style="font-size: 1.3rem; font-weight: 700; color: #667eea;">$${cost.toFixed(2)}</span>
            </div>
        `).join('')}
    `;
}

// ==================== TAB SWITCHING ====================

function switchTab(tabName) {
    // Update buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.tab === tabName) {
            btn.classList.add('active');
        }
    });

    // Update content
    document.querySelectorAll('.tab-pane').forEach(pane => {
        pane.classList.add('hidden');
    });
    document.getElementById(tabName + '-tab').classList.remove('hidden');
}

// ==================== UTILITIES ====================

function formatCurrency(amount) {
    if (amount >= 10000000) return '₹' + (amount / 10000000).toFixed(2) + ' Cr';
    if (amount >= 100000) return '₹' + (amount / 100000).toFixed(2) + ' L';
    return '₹' + amount.toFixed(2);
}

function showNotification(message, type) {
    const colors = {
        success: '#10b981',
        error: '#ef4444',
        info: '#3b82f6'
    };

    const div = document.createElement('div');
    div.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: ${colors[type]};
        color: white;
        padding: 15px 25px;
        border-radius: 10px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        z-index: 9999;
        font-weight: 600;
    `;
    div.textContent = message;
    document.body.appendChild(div);

    setTimeout(() => div.remove(), 3000);
}

function showError(message) {
    const errorDiv = document.getElementById('errorDisplay');
    errorDiv.className = 'alert-modern alert-danger';
    errorDiv.innerHTML = `<strong><i class="fas fa-exclamation-circle"></i> Error:</strong> ${message}`;
    errorDiv.classList.remove('hidden');

    // Scroll to error
    errorDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
