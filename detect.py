import os
import random
import logging

logger = logging.getLogger(__name__)

# Try to import Ultralytics YOLOv8 library.
# If not installed, we will use a fallback simulation.
YOLO_AVAILABLE = False
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    logger.warning("ultralytics package not found. YOLOv8 features will operate in simulation mode.")

class YOLOPackageClassifier:
    def __init__(self, model_path="weights/best.pt"):
        """Initializes the custom YOLOv8 model if available, otherwise sets up simulation mode."""
        self.model_path = model_path
        self.model = None
        self.classes = {0: "Paracetamol", 1: "Amoxicillin", 2: "Cetirizine", 3: "Pantoprazole", 4: "Unknown"}
        
        if YOLO_AVAILABLE:
            if os.path.exists(model_path):
                try:
                    self.model = YOLO(model_path)
                    logger.info(f"Loaded YOLOv8 custom weights from {model_path}")
                except Exception as e:
                    logger.error(f"Error loading YOLO weights: {e}. Defaulting to simulation.")
            else:
                logger.warning(f"YOLO weights not found at {model_path}. Running classifier in simulation mode.")
        
    def classify_image(self, img_source):
        """
        Classifies an image frame (or path) to identify the medicine package.
        Returns:
            tuple: (medicine_name, confidence_score)
        """
        # If real model is loaded, use it
        if self.model is not None:
            try:
                # Perform inference
                results = self.model(img_source, verbose=False)
                # Parse top 1 classification result
                for result in results:
                    if hasattr(result, 'probs') and result.probs is not None:
                        top1_idx = int(result.probs.top1)
                        confidence = float(result.probs.top1conf)
                        name = self.classes.get(top1_idx, "Unknown")
                        logger.info(f"YOLOv8 detected: {name} (conf: {confidence:.2f})")
                        return name, confidence
            except Exception as e:
                logger.error(f"YOLO inference error: {e}. Falling back to simulation.")

        # --- SIMULATION FALLBACK ---
        # If it's a filepath, inspect the name to simulate smart predictions
        if isinstance(img_source, str):
            filename = os.path.basename(img_source).lower()
            if "paracetamol" in filename:
                return "Paracetamol", 0.92
            elif "amoxicillin" in filename:
                return "Amoxicillin", 0.89
            elif "cetirizine" in filename:
                return "Cetirizine", 0.94
            elif "pantoprazole" in filename:
                return "Pantoprazole", 0.88

        # Otherwise, return random simulation
        detected_class = random.choice(["Paracetamol", "Amoxicillin", "Cetirizine", "Pantoprazole", "Unknown"])
        confidence = round(random.uniform(0.60, 0.95), 2)
        
        # If it's "Unknown", confidence is usually low or moderate
        if detected_class == "Unknown":
            confidence = round(random.uniform(0.30, 0.55), 2)
            
        logger.info(f"YOLOv8 (Simulated) detected: {detected_class} (conf: {confidence:.2f})")
        return detected_class, confidence

def mock_detect_package(image_source, weights_path="weights/best.pt"):
    """Convenience functional wrapper for YOLO classifier."""
    classifier = YOLOPackageClassifier(weights_path)
    return classifier.classify_image(image_source)
