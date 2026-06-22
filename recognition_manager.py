import os
import time
import logging
import cv2

# Safe imports for optional packages
EASYOCR_AVAILABLE = False
RAPIDFUZZ_AVAILABLE = False

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    logging.warning("easyocr package not found. Will run OCR in simulation mode.")

try:
    import rapidfuzz
    from rapidfuzz import process, fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    logging.warning("rapidfuzz package not found. Will run fuzzy matching in simulation mode.")

from database import log_detection, get_inventory_status, get_db_connection

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class RecognitionManager:
    def __init__(self, db_path=None):
        self.db_path = db_path
        self.reader = None
        
        # Initialize EasyOCR Reader with GPU disabled for CPU stability
        if EASYOCR_AVAILABLE:
            try:
                logger.info("Initializing EasyOCR Reader (CPU mode)...")
                # english language reader
                self.reader = easyocr.Reader(['en'], gpu=False)
                logger.info("EasyOCR Reader successfully initialized.")
            except Exception as e:
                logger.error(f"Failed to initialize EasyOCR Reader: {e}. Running OCR in simulation.")
                self.reader = None

    def capture_frame(self, camera_index=0, save_dir="static/captured"):
        """
        Captures a frame from the USB camera using OpenCV.
        Saves the captured image to disk and returns its file path.
        If camera is not available, simulates capture by saving a dummy image.
        """
        if not os.path.exists(save_dir):
            os.makedirs(save_dir, exist_ok=True)
            
        filename = f"capture_{int(time.time())}.jpg"
        filepath = os.path.join(save_dir, filename)

        cap = cv2.VideoCapture(camera_index)
        ret, frame = False, None
        
        if cap.isOpened():
            # Warm up camera
            for _ in range(5):
                cap.read()
            ret, frame = cap.read()
            cap.release()

        if ret and frame is not None:
            cv2.imwrite(filepath, frame)
            logger.info(f"Successfully captured camera frame saved to {filepath}")
            return filepath, frame
        else:
            logger.warning("No USB camera detected or failed to capture. Generating simulated frame...")
            # Generate dummy image with OpenCV for testing
            import numpy as np
            # Create a nice colorful gradient box representing a drug package
            dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.rectangle(dummy_frame, (100, 100), (540, 380), (76, 30, 20), -1) # Dark brown package
            cv2.rectangle(dummy_frame, (100, 100), (540, 380), (190, 140, 80), 3) # Golden borders
            
            # Put mock text on package
            simulated_medicines = ["Paracetamol", "Amoxicillin", "Cetirizine", "Pantoprazole", "UnknownDrug"]
            chosen_med = simulated_medicines[int(time.time()) % len(simulated_medicines)]
            
            cv2.putText(dummy_frame, "RX PRESCRIPTION", (150, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
            cv2.putText(dummy_frame, chosen_med.upper(), (150, 260), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (100, 255, 100), 3)
            cv2.putText(dummy_frame, "Lot: 4049281  Exp: 12/28", (150, 340), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

            cv2.imwrite(filepath, dummy_frame)
            logger.info(f"Simulated frame saved to {filepath} (Target medicine simulated: {chosen_med})")
            return filepath, dummy_frame

    def fuzzy_match_medicine(self, text):
        """
        Fuzzy matches extracted OCR text against registered medicines in the database.
        Returns:
            tuple: (matched_name, score) or (None, 0.0)
        """
        # Get active medicines
        status = get_inventory_status(self.db_path)
        med_names = [m["medicine_name"] for m in status]
        if not med_names:
            return None, 0.0

        if RAPIDFUZZ_AVAILABLE:
            # Match using RapidFuzz
            result = process.extractOne(text, med_names, scorer=fuzz.WRatio)
            if result:
                name, score, _ = result
                logger.info(f"Fuzzy matching '{text}' -> '{name}' (Score: {score:.1f})")
                return name, score
        else:
            # Fallback exact/substring matching
            clean_text = text.strip().lower()
            for name in med_names:
                if clean_text in name.lower() or name.lower() in clean_text:
                    logger.info(f"Fuzzy fallback match '{text}' -> '{name}'")
                    return name, 100.0
        return None, 0.0

    def process_ocr(self, img_source):
        """
        Attempts text extraction using EasyOCR.
        Returns highest confidence match or None.
        """
        if not EASYOCR_AVAILABLE or self.reader is None:
            # Simulate OCR by checking file content/name or simulation mode
            if isinstance(img_source, str) and os.path.exists(img_source):
                # Check for mock trigger strings
                filename = os.path.basename(img_source).lower()
                for med in ["paracetamol", "amoxicillin", "cetirizine", "pantoprazole"]:
                    if med in filename:
                        return med.capitalize(), 0.88
            return None, 0.0

        try:
            # OCR returns list of tuples: (bbox, text, confidence)
            results = self.reader.readtext(img_source)
            if not results:
                return None, 0.0

            best_match = None
            best_confidence = 0.0
            
            for bbox, text, confidence in results:
                logger.info(f"OCR extracted: '{text}' (conf: {confidence:.2f})")
                if confidence >= 0.75: # Confidence threshold
                    matched_name, match_score = self.fuzzy_match_medicine(text)
                    if match_score >= 80.0 and confidence > best_confidence:
                        best_confidence = confidence
                        best_match = matched_name

            if best_match:
                return best_match, best_confidence
        except Exception as e:
            logger.error(f"Error during EasyOCR processing: {e}")
            
        return None, 0.0

    def run_pipeline(self, image_path=None, camera_index=0):
        """
        Executes the recognition decision pipeline.
        Returns:
            dict: Decision outputs containing status, method, medicine, confidence, and compartment.
        """
        # 1. Capture image if not provided
        if not image_path:
            image_path, _ = self.capture_frame(camera_index)

        logger.info(f"Starting recognition pipeline on image: {image_path}")

        # 2. Attempt EasyOCR detection
        ocr_med, ocr_conf = self.process_ocr(image_path)
        if ocr_med:
            # Success via OCR
            log_detection("OCR", ocr_med, ocr_conf, self.db_path)
            comp_num = self._get_compartment_for_med(ocr_med)
            logger.info(f"OCR Pipeline Success: {ocr_med} assigned to Compartment {comp_num}")
            return {
                "status": "SUCCESS",
                "recognition_method": "OCR",
                "medicine_name": ocr_med,
                "confidence": ocr_conf,
                "compartment_number": comp_num,
                "image_path": image_path
            }

        # 3. Fallback to Human Verification
        logger.warning("AI fallback pipeline failed to identify package with confidence. Flagging for Human Verification.")
        log_detection("MANUAL_VERIFICATION", "Pending Review", 0.0, self.db_path)
        
        return {
            "status": "HUMAN_VERIFICATION",
            "recognition_method": "PENDING",
            "medicine_name": None,
            "confidence": 0.0,
            "compartment_number": None,
            "image_path": image_path
        }

    def _get_compartment_for_med(self, med_name):
        """Helper to get compartment mapped to a medicine name."""
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT compartment_number FROM medicines WHERE medicine_name = ?;", (med_name,))
            row = cursor.fetchone()
            return row["compartment_number"] if row else None

if __name__ == "__main__":
    # Test script for recognition manager
    manager = RecognitionManager()
    # Test on a simulated capture
    result = manager.run_pipeline()
    print("Pipeline Output:")
    print(result)
