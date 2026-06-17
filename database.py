import sqlite3
import os
from contextlib import contextmanager

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "med_rack.db")

@contextmanager
def get_db_connection(db_path=DEFAULT_DB_PATH):
    """Context manager for SQLite connections, ensuring transactions are committed and connections closed."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def init_db(db_path=DEFAULT_DB_PATH):
    """Initializes the SQLite database schemas and seeds default medicine mappings."""
    # Ensure directory exists
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    with get_db_connection(db_path) as conn:
        # 1. Medicines Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS medicines (
                medicine_id INTEGER PRIMARY KEY AUTOINCREMENT,
                medicine_name TEXT NOT NULL UNIQUE,
                compartment_number INTEGER UNIQUE CHECK (compartment_number BETWEEN 1 AND 4),
                barcode TEXT,
                reorder_threshold INTEGER DEFAULT 5
            );
        """)

        # 2. Inventory Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                inventory_id INTEGER PRIMARY KEY AUTOINCREMENT,
                medicine_id INTEGER UNIQUE,
                quantity INTEGER DEFAULT 0 CHECK (quantity >= 0),
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (medicine_id) REFERENCES medicines(medicine_id) ON DELETE CASCADE
            );
        """)

        # 3. Transactions Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                medicine_id INTEGER,
                action TEXT NOT NULL CHECK (action IN ('RESTOCK', 'RETRIEVE', 'MANUAL_ADJUST')),
                quantity INTEGER NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (medicine_id) REFERENCES medicines(medicine_id) ON DELETE CASCADE
            );
        """)

        # 4. Detections Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS detections (
                detection_id INTEGER PRIMARY KEY AUTOINCREMENT,
                recognition_method TEXT NOT NULL CHECK (recognition_method IN ('OCR', 'YOLO', 'MANUAL_VERIFICATION')),
                medicine_name TEXT,
                confidence REAL NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

    # Seed initial mappings if empty
    seed_db(db_path)

def seed_db(db_path=DEFAULT_DB_PATH):
    """Seeds default medicines for the 4 compartments if database is empty."""
    default_medicines = [
        {"name": "Paracetamol", "compartment": 1, "barcode": "8901043001023", "reorder": 5, "initial_qty": 15},
        {"name": "Amoxicillin", "compartment": 2, "barcode": "8901043001024", "reorder": 5, "initial_qty": 10},
        {"name": "Cetirizine", "compartment": 3, "barcode": "8901043001025", "reorder": 5, "initial_qty": 20},
        {"name": "Pantoprazole", "compartment": 4, "barcode": "8901043001026", "reorder": 5, "initial_qty": 8}
    ]

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM medicines;")
        if cursor.fetchone()[0] == 0:
            for med in default_medicines:
                # Insert medicine
                cursor.execute(
                    "INSERT INTO medicines (medicine_name, compartment_number, barcode, reorder_threshold) VALUES (?, ?, ?, ?);",
                    (med["name"], med["compartment"], med["barcode"], med["reorder"])
                )
                med_id = cursor.lastrowid
                # Insert inventory
                cursor.execute(
                    "INSERT INTO inventory (medicine_id, quantity) VALUES (?, ?);",
                    (med_id, med["initial_qty"])
                )
                # Log initial seed transaction
                cursor.execute(
                    "INSERT INTO transactions (medicine_id, action, quantity) VALUES (?, 'RESTOCK', ?);",
                    (med_id, med["initial_qty"])
                )
            print("Database successfully seeded with default medicines.")

def update_inventory_by_compartment(compartment_number, quantity_change, action_type, db_path=DEFAULT_DB_PATH):
    """
    Updates the inventory stock for the medicine mapped to a specific compartment.
    Calculates Inventory = Inventory + quantity_change. 
    Logs a transaction.
    Returns a dictionary of the updated status.
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # 1. Fetch medicine in that compartment
        cursor.execute(
            "SELECT medicine_id, medicine_name FROM medicines WHERE compartment_number = ?;",
            (compartment_number,)
        )
        med_row = cursor.fetchone()
        if not med_row:
            raise ValueError(f"No medicine mapped to compartment {compartment_number}")
        
        med_id, med_name = med_row["medicine_id"], med_row["medicine_name"]

        # 2. Get current inventory
        cursor.execute("SELECT quantity FROM inventory WHERE medicine_id = ?;", (med_id,))
        inv_row = cursor.fetchone()
        current_qty = inv_row["quantity"] if inv_row else 0

        # Calculate new quantity
        new_qty = current_qty + quantity_change
        if new_qty < 0:
            raise ValueError(f"Cannot subtract {abs(quantity_change)} from compartment {compartment_number}. Current stock: {current_qty}.")

        # 3. Update inventory
        cursor.execute(
            "UPDATE inventory SET quantity = ?, last_updated = CURRENT_TIMESTAMP WHERE medicine_id = ?;",
            (new_qty, med_id)
        )

        # 4. Insert transaction log
        cursor.execute(
            "INSERT INTO transactions (medicine_id, action, quantity) VALUES (?, ?, ?);",
            (med_id, action_type, quantity_change)
        )

        return {
            "medicine_id": med_id,
            "medicine_name": med_name,
            "compartment_number": compartment_number,
            "old_quantity": current_qty,
            "new_quantity": new_qty,
            "action": action_type,
            "quantity_changed": quantity_change
        }

def update_inventory_by_name(medicine_name, quantity_change, action_type, db_path=DEFAULT_DB_PATH):
    """Updates inventory using medicine name."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT medicine_id, compartment_number FROM medicines WHERE medicine_name = ?;",
            (medicine_name,)
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Medicine '{medicine_name}' is not registered in the system.")
        
        comp_num = row["compartment_number"]
        return update_inventory_by_compartment(comp_num, quantity_change, action_type, db_path)

def get_inventory_status(db_path=DEFAULT_DB_PATH):
    """Retrieves all medicines, their compartment, stock levels, and threshold alerts."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                m.medicine_id,
                m.medicine_name,
                m.compartment_number,
                m.barcode,
                m.reorder_threshold,
                COALESCE(i.quantity, 0) as quantity,
                i.last_updated
            FROM medicines m
            LEFT JOIN inventory i ON m.medicine_id = i.medicine_id
            ORDER BY m.compartment_number ASC;
        """)
        rows = cursor.fetchall()
        
        status_list = []
        for r in rows:
            qty = r["quantity"]
            threshold = r["reorder_threshold"]
            status_list.append({
                "medicine_id": r["medicine_id"],
                "medicine_name": r["medicine_name"],
                "compartment_number": r["compartment_number"],
                "barcode": r["barcode"],
                "reorder_threshold": threshold,
                "quantity": qty,
                "last_updated": r["last_updated"],
                "low_stock_alert": qty <= threshold
            })
        return status_list

def log_detection(method, name, confidence, db_path=DEFAULT_DB_PATH):
    """Logs a computer vision detection attempt."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO detections (recognition_method, medicine_name, confidence) VALUES (?, ?, ?);",
            (method, name, confidence)
        )
        return cursor.lastrowid

def get_recent_transactions(limit=10, db_path=DEFAULT_DB_PATH):
    """Returns the most recent stock transactions."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                t.transaction_id,
                m.medicine_name,
                m.compartment_number,
                t.action,
                t.quantity,
                t.timestamp
            FROM transactions t
            JOIN medicines m ON t.medicine_id = m.medicine_id
            ORDER BY t.transaction_id DESC
            LIMIT ?;
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

def get_recent_detections(limit=10, db_path=DEFAULT_DB_PATH):
    """Returns the most recent vision detections."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT detection_id, recognition_method, medicine_name, confidence, timestamp
            FROM detections
            ORDER BY detection_id DESC
            LIMIT ?;
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

if __name__ == "__main__":
    # If run directly, initialize database
    print("Initializing SQLite database...")
    init_db()
    print("Database initialization complete.")
    for item in get_inventory_status():
        print(f"Compartment {item['compartment_number']}: {item['medicine_name']} - Stock: {item['quantity']} (Alert: {item['low_stock_alert']})")
