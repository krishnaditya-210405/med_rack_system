import time
import logging
import threading

SERIAL_AVAILABLE = False
try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    logging.warning("pyserial package not found. Serial communication will run in simulation mode.")

logger = logging.getLogger(__name__)

class SerialCommunicator:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """Singleton pattern to ensure only one UART connection is active."""
        with cls._lock:
            if not cls._instance:
                cls._instance = super(SerialCommunicator, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, port="/dev/ttyACM0", baudrate=115200, timeout=1.5):
        if self._initialized:
            return
        
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        self.simulated = False
        self.conn_lock = threading.Lock()

        # Connect to hardware
        self.connect()
        self._initialized = True

    def connect(self):
        """Attempts to open the serial port. Falls back to simulation mode if it fails."""
        with self.conn_lock:
            if not SERIAL_AVAILABLE:
                self.simulated = True
                logger.info("pyserial unavailable. Initialized in VIRTUAL SERIAL SIMULATION mode.")
                return

            try:
                logger.info(f"Attempting UART Serial connection on {self.port} at {self.baudrate} baud...")
                self.ser = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=self.timeout,
                    write_timeout=self.timeout
                )
                self.simulated = False
                logger.info(f"UART connection established on {self.port}.")
                # Wait for ESP32 bootloader handshake
                time.sleep(2.0)
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
            except Exception as e:
                logger.error(f"Failed to connect to hardware UART: {e}.")
                self.simulated = True
                logger.warning("Defaulting to VIRTUAL SERIAL SIMULATION mode.")

    def disconnect(self):
        """Safely closes serial port."""
        with self.conn_lock:
            if self.ser and self.ser.is_open:
                try:
                    self.ser.close()
                    logger.info("UART serial port closed.")
                except Exception as e:
                    logger.error(f"Error closing serial port: {e}")
            self.ser = None

    def send_command(self, cmd: str, expected_ack: str = None, retries: int = 3, retry_delay: float = 0.5):
        """
        Sends a command via UART and awaits the expected ACK.
        Includes error handling, automatic reconnections, and command retries.
        """
        cmd_cleaned = cmd.strip()
        
        # Virtual Simulation Mode
        if self.simulated:
            logger.info(f"[UART SIMULATOR] Sent: '{cmd_cleaned}'")
            time.sleep(0.3) # Simulate communication delay
            
            # Formulate mock responses
            if expected_ack:
                mock_response = expected_ack
            elif cmd_cleaned == "STATUS":
                mock_response = "STATUS_OK: C1=CLOSED, C2=CLOSED, C3=CLOSED, C4=CLOSED"
            else:
                mock_response = f"ACK_{cmd_cleaned}"
                
            logger.info(f"[UART SIMULATOR] Recv: '{mock_response}'")
            return True, mock_response

        # Hardware UART Mode
        for attempt in range(1, retries + 1):
            with self.conn_lock:
                # Reconnect if connection dropped
                if not self.ser or not self.ser.is_open:
                    logger.warning("Serial connection lost. Re-connecting...")
                    try:
                        self.connect()
                    except Exception:
                        pass
                    if not self.ser or not self.ser.is_open:
                        time.sleep(retry_delay)
                        continue

                try:
                    # Clear buffers
                    self.ser.reset_input_buffer()
                    self.ser.reset_output_buffer()

                    # Write command with newline termination
                    logger.info(f"UART Tx (Attempt {attempt}/{retries}): '{cmd_cleaned}'")
                    self.ser.write(f"{cmd_cleaned}\n".encode('utf-8'))
                    self.ser.flush()

                    # Wait for response
                    response_bytes = self.ser.readline()
                    if not response_bytes:
                        logger.warning("UART Rx Timeout: No response received from ESP32.")
                        raise serial.SerialTimeoutException("Read timeout")

                    response = response_bytes.decode('utf-8').strip()
                    logger.info(f"UART Rx: '{response}'")

                    # Validate response
                    if expected_ack:
                        if expected_ack in response:
                            return True, response
                        else:
                            logger.warning(f"UART Rx Mismatch: Expected '{expected_ack}', got '{response}'")
                    else:
                        return True, response

                except (serial.SerialException, serial.SerialTimeoutException, OSError) as e:
                    logger.error(f"UART error during command '{cmd_cleaned}': {e}")
                    if self.ser:
                        try:
                            self.ser.close()
                        except Exception:
                            pass
                        self.ser = None

            time.sleep(retry_delay)

        logger.error(f"UART command '{cmd_cleaned}' failed after {retries} attempts.")
        return False, "TIMEOUT_OR_ERROR"

    def open_compartment(self, compartment_number: int) -> bool:
        """Helper to open a specific compartment lock."""
        cmd = f"OPEN_{compartment_number}"
        ack = f"ACK_OPEN_{compartment_number}"
        success, _ = self.send_command(cmd, expected_ack=ack)
        return success

    def close_compartment(self, compartment_number: int) -> bool:
        """Helper to close a specific compartment lock."""
        cmd = f"CLOSE_{compartment_number}"
        ack = f"ACK_CLOSE_{compartment_number}"
        success, _ = self.send_command(cmd, expected_ack=ack)
        return success

    def get_status(self) -> str:
        """Helper to fetch ESP32 controller status."""
        success, response = self.send_command("STATUS")
        if success:
            return response
        return "ERROR_FETCHING_STATUS"

if __name__ == "__main__":
    # Test script for communicator
    comm = SerialCommunicator(port="COM3")
    print("Testing Open Compartment 1...")
    res = comm.open_compartment(1)
    print(f"Result: {res}")
    
    print("Testing Status Query...")
    status = comm.get_status()
    print(f"Hardware Status: {status}")
