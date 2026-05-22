// boards manager ver.
// M5Stack by M5Stack official 2.0.9


#include <M5Core2.h>
#include "BluetoothSerial.h"

#if !defined(CONFIG_BT_ENABLED) || !defined(CONFIG_BLUEDROID_ENABLED)
#error Bluetooth is not enabled! Please enable it in the ESP32 settings.
#endif

const char* BT_NAME = "M5Stack-Core2-IMU";

BluetoothSerial SerialBT;

float accX, accY, accZ;
float gyrX, gyrY, gyrZ;

unsigned long lastSampleTime = 0;
const unsigned long SAMPLE_INTERVAL = 10;  // 100Hz = 10ms

bool oldClientConnected = false;

void drawStatus(bool connected) {
  M5.Lcd.fillScreen(BLACK);
  M5.Lcd.setTextColor(WHITE);
  M5.Lcd.setTextSize(2);
  M5.Lcd.setCursor(0, 0);
  M5.Lcd.println("BT Classic IMU");
  M5.Lcd.print("Name: ");
  M5.Lcd.println(BT_NAME);
  M5.Lcd.println();
  M5.Lcd.println(connected ? "Connected" : "Waiting for connection...");
}

void setup() {
  M5.begin();
  M5.IMU.Init();

  Serial.begin(115200);
  delay(100);

  if (!SerialBT.begin(BT_NAME)) {
    Serial.println("[BT] Bluetooth Classic init failed");
    M5.Lcd.fillScreen(BLACK);
    M5.Lcd.setTextColor(RED);
    M5.Lcd.setTextSize(2);
    M5.Lcd.setCursor(0, 0);
    M5.Lcd.println("BT init failed");
  } else {
    Serial.print("[BT] Bluetooth Classic started. Device name: ");
    Serial.println(BT_NAME);
    Serial.println("[BT] Pair/connect from PC or smartphone via Bluetooth SPP.");
    drawStatus(false);
  }

  lastSampleTime = millis();
}

void loop() {
  const bool clientConnected = SerialBT.hasClient();

  if (clientConnected != oldClientConnected) {
    drawStatus(clientConnected);
    oldClientConnected = clientConnected;
  }

  const unsigned long currentTime = millis();

  if (currentTime - lastSampleTime >= SAMPLE_INTERVAL) {
    lastSampleTime = currentTime;

    M5.IMU.getAccelData(&accX, &accY, &accZ);
    M5.IMU.getGyroData(&gyrX, &gyrY, &gyrZ);

    char dataBuffer[128];
    snprintf(dataBuffer, sizeof(dataBuffer),
             "%.2f,%.2f,%.2f,%.2f,%.2f,%.2f\n",
             accX, accY, accZ, gyrX, gyrY, gyrZ);

    if (clientConnected) {
      SerialBT.print(dataBuffer);
    }

    Serial.print(dataBuffer);
  }

  M5.update();
}
