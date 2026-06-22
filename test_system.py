import os
import unittest
import tempfile
import shutil
import database
from communication import SerialCommunicator
from recognition_manager import RecognitionManager

class TestMedRackSystem(unittest.TestCase):
    def setUp(self):
        # Create a temporary database file for isolated testing
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_med_rack.db")
        database.init_db(self.db_path)

    def tearDown(self):
        # Remove temporary database files
        shutil.rmtree(self.test_dir)

    def test_database_seeding(self):
        """Verify database is correctly seeded with the 4 default compartments."""
        status = database.get_inventory_status(self.db_path)
        self.assertEqual(len(status), 4, "Should seed exactly 4 default compartments.")
        
        # Test individual mappings
        meds = {item["compartment_number"]: item["medicine_name"] for item in status}
        self.assertEqual(meds[1], "Paracetamol")
        self.assertEqual(meds[2], "Amoxicillin")
        self.assertEqual(meds[3], "Cetirizine")
        self.assertEqual(meds[4], "Pantoprazole")

    def test_inventory_updates(self):
        """Test transaction logic, restocking, retrieving, and safety checks."""
        # 1. Restock Compartment 1 (Paracetamol)
        # Initial is 15 (see database.py seed)
        res = database.update_inventory_by_compartment(1, 5, 'RESTOCK', self.db_path)
        self.assertEqual(res["new_quantity"], 20)
        self.assertEqual(res["quantity_changed"], 5)
        
        # Verify transaction log was inserted
        tx_logs = database.get_recent_transactions(limit=1, db_path=self.db_path)
        self.assertEqual(len(tx_logs), 1)
        self.assertEqual(tx_logs[0]["medicine_name"], "Paracetamol")
        self.assertEqual(tx_logs[0]["action"], "RESTOCK")
        self.assertEqual(tx_logs[0]["quantity"], 5)

        # 2. Retrieve Compartment 1 (Subtracting)
        res_ret = database.update_inventory_by_compartment(1, -12, 'RETRIEVE', self.db_path)
        self.assertEqual(res_ret["new_quantity"], 8)
        
        # 3. Assert stock cannot go below zero
        with self.assertRaises(ValueError):
            # Try to subtract 10 when stock is 8
            database.update_inventory_by_compartment(1, -10, 'RETRIEVE', self.db_path)

    def test_detection_logging(self):
        """Verify computer vision recognition logging works correctly."""
        det_id = database.log_detection("OCR", "Amoxicillin", 0.82, self.db_path)
        self.assertIsNotNone(det_id)
        
        detections = database.get_recent_detections(limit=1, db_path=self.db_path)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0]["recognition_method"], "OCR")
        self.assertEqual(detections[0]["medicine_name"], "Amoxicillin")
        self.assertEqual(detections[0]["confidence"], 0.82)

    def test_serial_communication_mock(self):
        """Verify UART serial protocol behaves correctly under simulated connection."""
        comm = SerialCommunicator(port="COM_MOCK_TEST")
        # Ensure it falls back to simulation mode
        self.assertTrue(comm.simulated)
        
        # Test opening compartment
        success = comm.open_compartment(2)
        self.assertTrue(success)
        
        # Test closing compartment
        success_close = comm.close_compartment(4)
        self.assertTrue(success_close)
        
        # Test hardware status request
        status = comm.get_status()
        self.assertIn("STATUS_OK", status)



    def test_recognition_manager_pipeline(self):
        """Test entire vision fallback routing pipeline logic."""
        rec_mgr = RecognitionManager(self.db_path)
        
        # Run pipeline with a simulated captured image (will trigger simulated camera frame generation)
        result = rec_mgr.run_pipeline()
        
        # Verify result contains routing keys
        self.assertIn("status", result)
        self.assertIn("recognition_method", result)
        self.assertIn("image_path", result)
        
        # If success, must have mapped target compartment
        if result["status"] == "SUCCESS":
            self.assertIsNotNone(result["compartment_number"])
            self.assertIn(result["medicine_name"], ["Paracetamol", "Amoxicillin", "Cetirizine", "Pantoprazole"])
        else:
            self.assertEqual(result["status"], "HUMAN_VERIFICATION")
            self.assertIsNone(result["compartment_number"])

if __name__ == "__main__":
    print("====================================================")
    print("  RUNNING TESTS FOR MEDICINE RACK MANAGEMENT SYSTEM  ")
    print("====================================================")
    unittest.main()
