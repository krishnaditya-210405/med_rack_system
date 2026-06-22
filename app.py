import os
import logging
from flask import Flask, render_template, request, jsonify, url_for
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename

import database
from recognition_manager import RecognitionManager
from communication import SerialCommunicator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Flask App
app = Flask(__name__)
app.config['SECRET_KEY'] = 'med-rack-super-secret-key-123!'
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB Upload limit

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.root_path, 'static', 'captured'), exist_ok=True)

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize DB
database.init_db()

# Initialize AI Recognition Manager and Serial Communicator
recognition_mgr = RecognitionManager()
serial_comm = SerialCommunicator(port="/dev/ttyACM0") # Will automatically fall back to simulation if port unavailable

# Global state to keep track of current pending human verification
pending_verifications = {}

# --- WEB DASHBOARD ROUTES ---

@app.route('/')
def index():
    """Renders the main web administration dashboard."""
    inventory = database.get_inventory_status()
    transactions = database.get_recent_transactions(limit=8)
    detections = database.get_recent_detections(limit=8)
    
    # Check physical hardware status
    hardware_raw = serial_comm.get_status()
    is_simulated = serial_comm.simulated
    
    return render_template(
        'index.html',
        inventory=inventory,
        transactions=transactions,
        detections=detections,
        hardware_status=hardware_raw,
        is_simulated=is_simulated
    )

@app.route('/api/inventory', methods=['GET'])
def get_inventory():
    """Returns current inventory stock levels in JSON format."""
    return jsonify(database.get_inventory_status())

@app.route('/api/open/<int:compartment>', methods=['POST'])
def open_compartment(compartment):
    """Sends UART command to ESP32 to open the specified compartment."""
    if compartment < 1 or compartment > 4:
        return jsonify({"status": "ERROR", "message": "Invalid compartment number"}), 400
        
    logger.info(f"API request to turn ON Compartment {compartment} LED")
    success = serial_comm.open_compartment(compartment)
    
    if success:
        # Update WebSockets log and front-end status
        socketio.emit('log_message', {
            'type': 'info',
            'message': f"Compartment {compartment} LED turned ON successfully."
        })
        socketio.emit('hardware_update', {
            'compartment': compartment,
            'state': 'ON'
        })
        return jsonify({"status": "SUCCESS", "message": f"Compartment {compartment} LED turned ON"})
    else:
        socketio.emit('log_message', {
            'type': 'error',
            'message': f"Failed to send open command to Compartment {compartment} (UART timeout)."
        })
        return jsonify({"status": "ERROR", "message": "Hardware communication failed"}), 500

@app.route('/api/close/<int:compartment>', methods=['POST'])
def close_compartment(compartment):
    """Sends UART command to ESP32 to close the specified compartment."""
    if compartment < 1 or compartment > 4:
        return jsonify({"status": "ERROR", "message": "Invalid compartment number"}), 400
        
    logger.info(f"API request to turn OFF Compartment {compartment} LED")
    success = serial_comm.close_compartment(compartment)
    
    if success:
        socketio.emit('log_message', {
            'type': 'info',
            'message': f"Compartment {compartment} LED turned OFF successfully."
        })
        socketio.emit('hardware_update', {
            'compartment': compartment,
            'state': 'OFF'
        })
        return jsonify({"status": "SUCCESS", "message": f"Compartment {compartment} LED turned OFF"})
    else:
        socketio.emit('log_message', {
            'type': 'error',
            'message': f"Failed to send close command to Compartment {compartment} (UART timeout)."
        })
        return jsonify({"status": "ERROR", "message": "Hardware communication failed"}), 500

@app.route('/api/adjust', methods=['POST'])
def adjust_inventory():
    """Manually adjusts stock inventory without vision matching."""
    data = request.get_json() or {}
    compartment = data.get('compartment')
    amount = data.get('amount')
    action = data.get('action') # 'RESTOCK', 'RETRIEVE', 'MANUAL_ADJUST'
    
    if not compartment or amount is None or not action:
        return jsonify({"status": "ERROR", "message": "Missing required fields"}), 400
        
    try:
        amount = int(amount)
        # For retrieval, inventory change should be negative
        change = -amount if action == 'RETRIEVE' else amount
        
        result = database.update_inventory_by_compartment(compartment, change, action)
        
        # Broadcast stock update & log event
        socketio.emit('inventory_change', {
            'inventory': database.get_inventory_status(),
            'recent_transactions': database.get_recent_transactions(limit=8)
        })
        socketio.emit('log_message', {
            'type': 'success',
            'message': f"Stock adjusted for Compartment {compartment} ({result['medicine_name']}): {change:+} units."
        })
        
        return jsonify({"status": "SUCCESS", "data": result})
    except Exception as e:
        logger.error(f"Error adjusting inventory: {e}")
        return jsonify({"status": "ERROR", "message": str(e)}), 400

@app.route('/api/upload', methods=['POST'])
def upload_prescription():
    """
    Accepts an uploaded image, runs the fallback AI recognition pipeline,
    and returns matched data or triggers human verification if confidence is low.
    """
    if 'file' not in request.files:
        return jsonify({"status": "ERROR", "message": "No file uploaded"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "ERROR", "message": "No file selected"}), 400

    if file:
        filename = secure_filename(file.filename)
        # Unique prefix to avoid naming collision
        filename = f"uploaded_{int(time_custom())}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Run recognition pipeline
        result = recognition_mgr.run_pipeline(image_path=filepath)
        
        # Format the relative image path for template display
        relative_path = url_for('static', filename=f"uploads/{filename}")
        result['web_image_path'] = relative_path
        
        if result['status'] == 'SUCCESS':
            # Auto update transactions list on front end
            socketio.emit('log_message', {
                'type': 'success',
                'message': f"AI matched package: {result['medicine_name']} ({result['recognition_method']} - Conf: {result['confidence']:.2%})"
            })
            
            # Emit live detection list update
            socketio.emit('detections_change', {
                'recent_detections': database.get_recent_detections(limit=8)
            })
            
            return jsonify(result)
        else:
            # Requires human verification
            verif_id = f"verif_{int(time_custom())}"
            pending_verifications[verif_id] = filepath
            
            result['verif_id'] = verif_id
            
            # Notify UI that manual intervention is required
            socketio.emit('log_message', {
                'type': 'warning',
                'message': "AI confidence below threshold. Human Verification required!"
            })
            socketio.emit('human_verification_required', result)
            
            return jsonify(result)

@app.route('/api/verify', methods=['POST'])
def manual_verify():
    """Handles manual fallback submissions when AI confidence is low."""
    data = request.get_json() or {}
    verif_id = data.get('verif_id')
    compartment = data.get('compartment')
    amount = data.get('amount', 0)
    action = data.get('action', 'RESTOCK') # RESTOCK or RETRIEVE
    
    if not verif_id or not compartment:
        return jsonify({"status": "ERROR", "message": "Missing verification parameters"}), 400
        
    filepath = pending_verifications.pop(verif_id, None)
    if not filepath:
        return jsonify({"status": "ERROR", "message": "Invalid or expired verification session"}), 404
        
    try:
        compartment = int(compartment)
        amount = int(amount)
        change = -amount if action == 'RETRIEVE' else amount
        
        # Perform db update
        result = database.update_inventory_by_compartment(compartment, change, 'MANUAL_ADJUST')
        
        # Log manual detection override
        database.log_detection("MANUAL_VERIFICATION", result['medicine_name'], 1.0)
        
        # Broadcast changes
        socketio.emit('inventory_change', {
            'inventory': database.get_inventory_status(),
            'recent_transactions': database.get_recent_transactions(limit=8)
        })
        socketio.emit('detections_change', {
            'recent_detections': database.get_recent_detections(limit=8)
        })
        socketio.emit('log_message', {
            'type': 'success',
            'message': f"Manual Verification complete. Compartment {compartment} ({result['medicine_name']}) stock adjusted."
        })
        
        return jsonify({"status": "SUCCESS", "data": result})
    except Exception as e:
        logger.error(f"Manual verification error: {e}")
        return jsonify({"status": "ERROR", "message": str(e)}), 400

@app.route('/api/camera-scan', methods=['POST'])
def camera_scan():
    """Triggers USB camera capture and processes frame through AI pipeline."""
    try:
        result = recognition_mgr.run_pipeline()
        
        # Format the relative image path
        filename = os.path.basename(result['image_path'])
        relative_path = url_for('static', filename=f"captured/{filename}")
        result['web_image_path'] = relative_path
        
        if result['status'] == 'SUCCESS':
            socketio.emit('log_message', {
                'type': 'success',
                'message': f"Camera Scan Matched: {result['medicine_name']} via {result['recognition_method']} (Conf: {result['confidence']:.2%})"
            })
            socketio.emit('detections_change', {
                'recent_detections': database.get_recent_detections(limit=8)
            })
            return jsonify(result)
        else:
            verif_id = f"verif_{int(time_custom())}"
            pending_verifications[verif_id] = result['image_path']
            result['verif_id'] = verif_id
            
            socketio.emit('log_message', {
                'type': 'warning',
                'message': "Camera Scan failed to match package. Flagged for Human Verification."
            })
            socketio.emit('human_verification_required', result)
            return jsonify(result)
            
    except Exception as e:
        logger.error(f"Camera scanning error: {e}")
        return jsonify({"status": "ERROR", "message": str(e)}), 500

@app.route('/api/hardware-status', methods=['GET'])
def get_hardware_status():
    """Queries UART for hardware status."""
    status = serial_comm.get_status()
    return jsonify({
        "raw_status": status,
        "simulated": serial_comm.simulated
    })

def time_custom():
    import time
    return time.time()

if __name__ == '__main__':
    # Start the Flask SocketIO server
    logger.info("Starting AI-Powered Medicine Rack System Dashboard...")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
