/**
 * AI-Powered Medicine Rack Management System - ESP32 Firmware
 * Controls 4 PWM Servos representing lock latches for Compartments 1-4.
 * Communicates with Raspberry Pi over UART (115200 Baud).
 */

#include <ESP32Servo.h>

// Servo pin mappings
#define SERVO_1_PIN 18
#define SERVO_2_PIN 19
#define SERVO_3_PIN 21
#define SERVO_4_PIN 22

// Servo instances
Servo servo1;
Servo servo2;
Servo servo3;
Servo servo4;

// Lock states (true = OPEN/unlocked [90 deg], false = CLOSED/locked [0 deg])
bool lock1_open = false;
bool lock2_open = false;
bool lock3_open = false;
bool lock4_open = false;

// Angle configurations
const int ANGLE_LOCKED = 0;
const int ANGLE_UNLOCKED = 90;

// Serial buffer
String inputBuffer = "";

void setup() {
  // Initialize UART Serial Communication
  Serial.begin(115200);
  while (!Serial) {
    ; // Wait for serial port to connect (needed for native USB port only)
  }
  
  // Allow allocation of all timers for ESP32Servo
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);

  // Set frequencies
  servo1.setPeriodHertz(50); // Standard 50hz servo
  servo2.setPeriodHertz(50);
  servo3.setPeriodHertz(50);
  servo4.setPeriodHertz(50);

  // Attach servos to pins
  servo1.attach(SERVO_1_PIN, 500, 2400); // Attach with min/max pulse width in microseconds
  servo2.attach(SERVO_2_PIN, 500, 2400);
  servo3.attach(SERVO_3_PIN, 500, 2400);
  servo4.attach(SERVO_4_PIN, 500, 2400);

  // Initialize all locks to LOCKED (Closed) state on boot
  servo1.write(ANGLE_LOCKED);
  servo2.write(ANGLE_LOCKED);
  servo3.write(ANGLE_LOCKED);
  servo4.write(ANGLE_LOCKED);
  
  delay(500); // Give servos time to position
  
  // Send startup message
  Serial.println("SYSTEM_BOOT_SUCCESS: ESP32 Medicine Rack Controller Ready.");
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
    servo1.write(ANGLE_UNLOCKED);
    lock1_open = true;
    delay(300); // Wait for servo to sweep
    Serial.println("ACK_OPEN_1");
  } 
  else if (command == "CLOSE_1") {
    servo1.write(ANGLE_LOCKED);
    lock1_open = false;
    delay(300);
    Serial.println("ACK_CLOSE_1");
  }
  
  // Compartment 2 Commands
  else if (command == "OPEN_2") {
    servo2.write(ANGLE_UNLOCKED);
    lock2_open = true;
    delay(300);
    Serial.println("ACK_OPEN_2");
  } 
  else if (command == "CLOSE_2") {
    servo2.write(ANGLE_LOCKED);
    lock2_open = false;
    delay(300);
    Serial.println("ACK_CLOSE_2");
  }
  
  // Compartment 3 Commands
  else if (command == "OPEN_3") {
    servo3.write(ANGLE_UNLOCKED);
    lock3_open = true;
    delay(300);
    Serial.println("ACK_OPEN_3");
  } 
  else if (command == "CLOSE_3") {
    servo3.write(ANGLE_LOCKED);
    lock3_open = false;
    delay(300);
    Serial.println("ACK_CLOSE_3");
  }
  
  // Compartment 4 Commands
  else if (command == "OPEN_4") {
    servo4.write(ANGLE_UNLOCKED);
    lock4_open = true;
    delay(300);
    Serial.println("ACK_OPEN_4");
  } 
  else if (command == "CLOSE_4") {
    servo4.write(ANGLE_LOCKED);
    lock4_open = false;
    delay(300);
    Serial.println("ACK_CLOSE_4");
  }
  
  // Status Query Command
  else if (command == "STATUS") {
    String statusStr = "STATUS_OK: C1=" + String(lock1_open ? "OPEN" : "CLOSED") +
                       ", C2=" + String(lock2_open ? "OPEN" : "CLOSED") +
                       ", C3=" + String(lock3_open ? "OPEN" : "CLOSED") +
                       ", C4=" + String(lock4_open ? "OPEN" : "CLOSED");
    Serial.println(statusStr);
  }
  
  // Unknown Command Fallback
  else {
    Serial.print("ERROR_UNKNOWN_COMMAND: ");
    Serial.println(command);
  }
}
