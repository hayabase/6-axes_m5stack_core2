// boards manager ver.
// M5Stack by M5Stack official 2.0.9
//
// 必要ライブラリ:
// - M5Unified
// - BluetoothSerial はESP32環境に含まれています
#include <M5Unified.h>
#include "BluetoothSerial.h"
#if !defined(CONFIG_BT_ENABLED) || !defined(CONFIG_BLUEDROID_ENABLED)
#error Bluetooth is not enabled! Please enable it in the ESP32 settings.
#endif
const char* BT_NAME = "M5Stack-Core2-IMU";
BluetoothSerial SerialBT;
// サンプリング設定
unsigned long lastSampleTime = 0;
const unsigned long SAMPLE_INTERVAL = 10;  // 100Hz = 10ms
bool oldClientConnected = false;
// 表示更新用
void drawStatus(bool connected) {
  M5.Display.fillScreen(BLACK);
  M5.Display.setTextColor(WHITE);
  M5.Display.setTextSize(2);
  M5.Display.setCursor(0, 0);
  M5.Display.println("BT Classic IMU");
  M5.Display.print("Name: ");
  M5.Display.println(BT_NAME);
  M5.Display.println();
  if (connected) {
    M5.Display.setTextColor(GREEN);
    M5.Display.println("Connected");
  } else {
    M5.Display.setTextColor(YELLOW);
    M5.Display.println("Waiting...");
  }
  M5.Display.setTextColor(WHITE);
  M5.Display.println();
  M5.Display.println("Format:");
  M5.Display.println("accX,accY,accZ,");
  M5.Display.println("gyrX,gyrY,gyrZ");
}
void setup() {
  Serial.begin(115200);
  delay(500);
  // M5Stack Core2 初期化
  auto cfg = M5.config();
  M5.begin(cfg);
  M5.Display.fillScreen(BLACK);
  M5.Display.setTextColor(WHITE);
  M5.Display.setTextSize(2);
  M5.Display.setCursor(0, 0);
  M5.Display.println("M5 Core2 IMU");
  M5.Display.println("Initializing...");
  Serial.println("M5 Core2 IMU Bluetooth Classic Start");
  // IMUが使えるか確認
  if (!M5.Imu.isEnabled()) {
    Serial.println("[IMU] IMU is not enabled.");
    M5.Display.fillScreen(BLACK);
    M5.Display.setTextColor(RED);
    M5.Display.setCursor(0, 0);
    M5.Display.println("IMU not enabled");
    M5.Display.println("Check library");
    M5.Display.println("or board setting.");
    while (true) {
      delay(1000);
    }
  }
  Serial.println("[IMU] IMU enabled.");
  // Bluetooth Classic SPP 開始
  if (!SerialBT.begin(BT_NAME)) {
    Serial.println("[BT] Bluetooth Classic init failed");
    M5.Display.fillScreen(BLACK);
    M5.Display.setTextColor(RED);
    M5.Display.setTextSize(2);
    M5.Display.setCursor(0, 0);
    M5.Display.println("BT init failed");
    while (true) {
      delay(1000);
    }
  }
  Serial.print("[BT] Bluetooth Classic started. Device name: ");
  Serial.println(BT_NAME);
  Serial.println("[BT] Pair/connect from PC or smartphone via Bluetooth SPP.");
  Serial.println("accX,accY,accZ,gyrX,gyrY,gyrZ");
  drawStatus(false);
  lastSampleTime = millis();
}
void loop() {
  M5.update();
  const bool clientConnected = SerialBT.hasClient();
  if (clientConnected != oldClientConnected) {
    drawStatus(clientConnected);
    oldClientConnected = clientConnected;
  }
  const unsigned long currentTime = millis();
  if (currentTime - lastSampleTime >= SAMPLE_INTERVAL) {
    lastSampleTime = currentTime;
    // IMUデータを更新できたときだけ読む
    if (M5.Imu.update()) {
      auto imuData = M5.Imu.getImuData();
      float accX = imuData.accel.x;
      float accY = imuData.accel.y;
      float accZ = imuData.accel.z;
      float gyrX = imuData.gyro.x;
      float gyrY = imuData.gyro.y;
      float gyrZ = imuData.gyro.z;
      char dataBuffer[128];
      // 小数4桁で出力
      // 加速度: g 単位
      // 角速度: deg/s 単位
      snprintf(dataBuffer, sizeof(dataBuffer),
               "%.4f,%.4f,%.4f,%.4f,%.4f,%.4f\n",
               accX, accY, accZ, gyrX, gyrY, gyrZ);
      // Bluetooth接続中ならBluetoothにも送信
      if (clientConnected) {
        SerialBT.print(dataBuffer);
      }
      // USBシリアルにも出力
      Serial.print(dataBuffer);
    } else {
      Serial.println("[IMU] update failed");
    }
  }
}