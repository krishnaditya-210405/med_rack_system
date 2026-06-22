// Initialize WebSocket connection
const socket = io();

// Get UI Elements
const logsContainer = document.getElementById('logs-container');
const adjustModal = document.getElementById('adjust-modal');
const verifyModal = document.getElementById('verify-modal');
const dropArea = document.getElementById('drop-area');
const previewPanel = document.getElementById('scan-preview-panel');

// --- Socket.IO Event Listeners ---

// Listen for system status logs
socket.on('log_message', function(data) {
    appendLog(data.message, data.type);
});

// Listen for hardware lock updates
socket.on('hardware_update', function(data) {
    const badge = document.getElementById(`lock-badge-${data.compartment}`);
    if (badge) {
        badge.textContent = data.state;
        if (data.state === 'ON' || data.state === 'OPEN') {
            badge.classList.add('open');
        } else {
            badge.classList.remove('open');
        }
    }
});

// Listen for inventory stock changes
socket.on('inventory_change', function(data) {
    updateInventoryUI(data.inventory);
    updateTransactionsTable(data.recent_transactions);
});

// Listen for vision detection changes
socket.on('detections_change', function(data) {
    updateDetectionsTable(data.recent_detections);
});

// Listen for AI fallback verification triggers
socket.on('human_verification_required', function(data) {
    document.getElementById('verify-session-id').value = data.verif_id;
    document.getElementById('verify-modal-img').src = data.web_image_path;
    openVerificationModal();
});

// --- Helper Functions ---

// Append entry to live log terminal
function appendLog(message, type = 'info') {
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    
    const now = new Date();
    const timeStr = now.toTimeString().split(' ')[0];
    
    entry.innerHTML = `
        <span class="log-timestamp">[${timeStr}]</span>
        <span class="log-text">${message}</span>
    `;
    
    logsContainer.appendChild(entry);
    logsContainer.scrollTop = logsContainer.scrollHeight;
}

// Update inventory stock cards dynamically
function updateInventoryUI(inventory) {
    let lowStockCount = 0;
    
    inventory.forEach(item => {
        const qtySpan = document.getElementById(`med-qty-${item.compartment_number}`);
        const card = document.getElementById(`comp-card-${item.compartment_number}`);
        
        if (qtySpan) {
            qtySpan.textContent = item.quantity;
        }
        
        if (card) {
            if (item.low_stock_alert) {
                card.classList.add('low-stock');
                lowStockCount++;
            } else {
                card.classList.remove('low-stock');
            }
        }
    });

    const globalAlertBadge = document.getElementById('low-stock-global-badge');
    if (globalAlertBadge) {
        if (lowStockCount > 0) {
            globalAlertBadge.textContent = `⚠️ ${lowStockCount} alert(s)`;
            globalAlertBadge.style.color = 'var(--accent-orange)';
        } else {
            globalAlertBadge.textContent = '✅ All stocks nominal';
            globalAlertBadge.style.color = 'var(--accent-teal)';
        }
    }
}

// Update recent transactions log table
function updateTransactionsTable(transactions) {
    const tbody = document.querySelector('#transactions-table tbody');
    if (!tbody) return;
    
    tbody.innerHTML = '';
    transactions.forEach(tx => {
        const timePart = tx.timestamp.includes(' ') ? tx.timestamp.split(' ')[1] : tx.timestamp;
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${timePart}</td>
            <td>${tx.medicine_name}</td>
            <td>${tx.compartment_number}</td>
            <td><span class="badge-action ${tx.action.lower()}">${tx.action}</span></td>
            <td>${tx.quantity}</td>
        `;
        tbody.appendChild(row);
    });
}

// Update recent vision detections table
function updateDetectionsTable(detections) {
    const tbody = document.querySelector('#detections-table tbody');
    if (!tbody) return;
    
    tbody.innerHTML = '';
    detections.forEach(det => {
        const timePart = det.timestamp.includes(' ') ? det.timestamp.split(' ')[1] : det.timestamp;
        const row = document.createElement('tr');
        const confPct = det.confidence ? (det.confidence * 100).toFixed(1) + '%' : '0%';
        row.innerHTML = `
            <td>${timePart}</td>
            <td>${det.recognition_method}</td>
            <td>${det.medicine_name || 'Pending Review'}</td>
            <td>${confPct}</td>
        `;
        tbody.appendChild(row);
    });
}

// --- Action Triggers (API requests) ---

// Open a compartment lock
async function triggerOpen(compartment) {
    appendLog(`Requesting LED ON command for Compartment ${compartment}...`, 'info');
    try {
        const response = await fetch(`/api/open/${compartment}`, { method: 'POST' });
        const data = await response.json();
        if (data.status !== 'SUCCESS') {
            alert(`Error: ${data.message}`);
        }
    } catch (err) {
        appendLog(`Network error sending LED ON command: ${err}`, 'error');
    }
}

// Close a compartment lock
async function triggerClose(compartment) {
    appendLog(`Requesting LED OFF command for Compartment ${compartment}...`, 'info');
    try {
        const response = await fetch(`/api/close/${compartment}`, { method: 'POST' });
        const data = await response.json();
        if (data.status !== 'SUCCESS') {
            alert(`Error: ${data.message}`);
        }
    } catch (err) {
        appendLog(`Network error sending LED OFF command: ${err}`, 'error');
    }
}

// --- Modals Management ---

// Modal 1: Adjustment
function openAdjustmentModal() {
    adjustModal.style.display = 'flex';
}
function closeAdjustmentModal() {
    adjustModal.style.display = 'none';
}

async function submitAdjustment() {
    const compartment = parseInt(document.getElementById('adjust-compartment').value);
    const action = document.getElementById('adjust-action').value;
    const amount = parseInt(document.getElementById('adjust-amount').value);
    
    if (isNaN(amount) || amount <= 0) {
        alert("Please enter a valid stock quantity");
        return;
    }

    try {
        const response = await fetch('/api/adjust', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ compartment, action, amount })
        });
        const resData = await response.json();
        if (resData.status === 'SUCCESS') {
            closeAdjustmentModal();
        } else {
            alert(`Error: ${resData.message}`);
        }
    } catch (err) {
        alert(`Failed to complete adjustment transaction: ${err}`);
    }
}

// Modal 2: Human Verification Override
function openVerificationModal() {
    verifyModal.style.display = 'flex';
}
function closeVerificationModal() {
    verifyModal.style.display = 'none';
}

async function submitVerification() {
    const verif_id = document.getElementById('verify-session-id').value;
    const compartment = parseInt(document.getElementById('verify-compartment').value);
    const action = document.getElementById('verify-action').value;
    const amount = parseInt(document.getElementById('verify-amount').value);

    if (isNaN(amount) || amount <= 0) {
        alert("Please enter a valid stock quantity");
        return;
    }

    try {
        const response = await fetch('/api/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ verif_id, compartment, action, amount })
        });
        const resData = await response.json();
        if (resData.status === 'SUCCESS') {
            closeVerificationModal();
            // Clear preview matching text
            document.getElementById('preview-matched-med').textContent = "Manually Verified";
            document.getElementById('preview-matched-method').textContent = "Method: Human Override";
            document.getElementById('preview-matched-conf').textContent = "Confidence: 100%";
        } else {
            alert(`Error: ${resData.message}`);
        }
    } catch (err) {
        alert(`Failed to confirm verification: ${err}`);
    }
}

// --- Image Scanning Flows ---

// USB Camera Scan
async function triggerCameraScan() {
    appendLog("Activating USB camera stream. Capturing frame...", 'info');
    previewPanel.style.display = 'none';
    
    try {
        const response = await fetch('/api/camera-scan', { method: 'POST' });
        const data = await response.json();
        
        displayScanResult(data);
    } catch (err) {
        appendLog(`Error capturing or processing camera frame: ${err}`, 'error');
    }
}

// Handle Drag and Drop
['dragenter', 'dragover'].forEach(eventName => {
    dropArea.addEventListener(eventName, e => {
        e.preventDefault();
        dropArea.classList.add('dragover');
    }, false);
});

['dragleave', 'drop'].forEach(eventName => {
    dropArea.addEventListener(eventName, e => {
        e.preventDefault();
        dropArea.classList.remove('dragover');
    }, false);
});

dropArea.addEventListener('drop', e => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length > 0) {
        uploadFile(files[0]);
    }
});

function handleFileSelect(inputElement) {
    if (inputElement.files.length > 0) {
        uploadFile(inputElement.files[0]);
    }
}

async function uploadFile(file) {
    appendLog(`Uploading file '${file.name}' for AI package OCR classification...`, 'info');
    previewPanel.style.display = 'none';

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        displayScanResult(data);
    } catch (err) {
        appendLog(`Upload process failed: ${err}`, 'error');
    }
}

function displayScanResult(result) {
    // Show preview box
    previewPanel.style.display = 'block';
    document.getElementById('preview-image').src = result.image_path;

    if (result.status === 'SUCCESS') {
        document.getElementById('preview-matched-med').textContent = result.medicine_name;
        document.getElementById('preview-matched-method').textContent = `Method: ${result.recognition_method}`;
        document.getElementById('preview-matched-conf').textContent = `Confidence: ${(result.confidence * 100).toFixed(1)}%`;
        
        // Auto open compartment
        appendLog(`AI pipeline matched medicine '${result.medicine_name}' in Compartment ${result.compartment_number} (${(result.confidence * 100).toFixed(0)}% conf). Turning ON indicator LED...`, 'success');
        triggerOpen(result.compartment_number);
    } else {
        document.getElementById('preview-matched-med').textContent = "Verification Required";
        document.getElementById('preview-matched-method').textContent = "Method: Fallback Triggered";
        document.getElementById('preview-matched-conf').textContent = "Confidence: < 75%";
        
        // Populate and open human verification modal
        document.getElementById('verify-session-id').value = result.verif_id;
        document.getElementById('verify-modal-img').src = result.web_image_path;
        openVerificationModal();
    }
}

// Initial stock updates on load
window.onload = function() {
    // Perform a status check for low stock alerts on startup
    fetch('/api/inventory')
        .then(res => res.json())
        .then(data => updateInventoryUI(data));
};
