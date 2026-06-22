/**
 * AI-Powered Medicine Rack Management System - ESP32 Firmware (LED Version)
 * Controls 4 LEDs representing indicators for Compartments 1-4.
 * Communicates with Raspberry Pi over UART (115200 Baud).
 */

// LED pin mappings
#define LED_1_PIN 18
#define LED_2_PIN 19
#define LED_3_PIN 21
#define LED_4_PIN 22

// LED states (true = ON, false = OFF)
bool led1_on = false;
bool led2_on = false;
bool led3_on = false;
bool led4_on = false;

// Serial buffer
String inputBuffer = "";

void setup() {
  // Initialize UART Serial Communication
  Serial.begin(115200);
  while (!Serial) {
    ; // Wait for serial port to connect (needed for native USB port only)
  }

  // Configure LED pins as OUTPUT
  pinMode(LED_1_PIN, OUTPUT);
  pinMode(LED_2_PIN, OUTPUT);
  pinMode(LED_3_PIN, OUTPUT);
  pinMode(LED_4_PIN, OUTPUT);

  // Initialize all LEDs to OFF state on boot
  digitalWrite(LED_1_PIN, LOW);
  digitalWrite(LED_2_PIN, LOW);
  digitalWrite(LED_3_PIN, LOW);
  digitalWrite(LED_4_PIN, LOW);
  
  delay(100);
  
  // Send startup message
  Serial.println("SYSTEM_BOOT_SUCCESS: ESP32 Medicine Rack LED Controller Ready.");
}

void loop() {
  // Read incoming serial commands from Raspberry Pi
  while (Serial.available() > 0) {
    char inChar = (char)Serial.read();
    
    // Command is terminated by a newline
    if (inChar == '\n') {
      inputBuffer.trim(); // Clean whitespace
      processCommand(inputBuffer);
      inputBuffer = ""; // Reset buffer
    } else if (inChar != '\r') {
      // Append char to command (skip carriage return)
      inputBuffer += inChar;
    }
  }
}

/**
 * Parses and executes incoming serial commands.
 */
void processCommand(String command) {
  if (command == "") return;

  // Compartment 1 Commands
  if (command == "OPEN_1") {
    digitalWrite(LED_1_PIN, HIGH);
    led1_on = true;
    Serial.println("ACK_OPEN_1");
  } 
  else if (command == "CLOSE_1") {
    digitalWrite(LED_1_PIN, LOW);
    led1_on = false;
    Serial.println("ACK_CLOSE_1");
  }
  
  // Compartment 2 Commands
  else if (command == "OPEN_2") {
    digitalWrite(LED_2_PIN, HIGH);
    led2_on = true;
    Serial.println("ACK_OPEN_2");
  } 
  else if (command == "CLOSE_2") {
    digitalWrite(LED_2_PIN, LOW);
    led2_on = false;
    Serial.println("ACK_CLOSE_2");
  }
  
  // Compartment 3 Commands
  else if (command == "OPEN_3") {
    digitalWrite(LED_3_PIN, HIGH);
    led3_on = true;
    Serial.println("ACK_OPEN_3");
  } 
  else if (command == "CLOSE_3") {
    digitalWrite(LED_3_PIN, LOW);
    led3_on = false;
    Serial.println("ACK_CLOSE_3");
  }
  
  // Compartment 4 Commands
  else if (command == "OPEN_4") {
    digitalWrite(LED_4_PIN, HIGH);
    led4_on = true;
    Serial.println("ACK_OPEN_4");
  } 
  else if (command == "CLOSE_4") {
    digitalWrite(LED_4_PIN, LOW);
    led4_on = false;
    Serial.println("ACK_CLOSE_4");
  }
  
  // Status Query Command
  else if (command == "STATUS") {
    String statusStr = "STATUS_OK: C1=" + String(led1_on ? "ON" : "OFF") +
                       ", C2=" + String(led2_on ? "ON" : "OFF") +
                       ", C3=" + String(led3_on ? "ON" : "OFF") +
                       ", C4=" + String(led4_on ? "ON" : "OFF");
    Serial.println(statusStr);
  }
  
  // Unknown Command Fallback
  else {
    Serial.print("ERROR_UNKNOWN_COMMAND: ");
    Serial.println(command);
  }
}
