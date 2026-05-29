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
const char* BT_NAME_PREFIX = "M5Stack-IMU_1";
char btName[32];
BluetoothSerial SerialBT;
// サンプリング設定
const unsigned long SAMPLE_INTERVAL = 10;  // 100Hz = 10ms
uint32_t sampleIndex = 0;
bool oldClientConnected = false;
const bool SEND_USB_SERIAL = false;
const size_t SAMPLE_BUFFER_SIZE = 128;
struct ImuSample {
  uint32_t index;
  uint32_t timeMs;
  float accX;
  float accY;
  float accZ;
  float gyrX;
  float gyrY;
  float gyrZ;
};
ImuSample sampleBuffer[SAMPLE_BUFFER_SIZE];
size_t sampleReadIndex = 0;
size_t sampleWriteIndex = 0;
size_t bufferedSamples = 0;
uint32_t droppedBufferedSamples = 0;
portMUX_TYPE sampleBufferMux = portMUX_INITIALIZER_UNLOCKED;

void clearSampleBuffer() {
  portENTER_CRITICAL(&sampleBufferMux);
  sampleReadIndex = 0;
  sampleWriteIndex = 0;
  bufferedSamples = 0;
  portEXIT_CRITICAL(&sampleBufferMux);
}

void pushSample(const ImuSample& sample) {
  portENTER_CRITICAL(&sampleBufferMux);
  if (bufferedSamples >= SAMPLE_BUFFER_SIZE) {
    sampleReadIndex = (sampleReadIndex + 1) % SAMPLE_BUFFER_SIZE;
    bufferedSamples--;
    droppedBufferedSamples++;
  }

  sampleBuffer[sampleWriteIndex] = sample;
  sampleWriteIndex = (sampleWriteIndex + 1) % SAMPLE_BUFFER_SIZE;
  bufferedSamples++;
  portEXIT_CRITICAL(&sampleBufferMux);
}

bool popSample(ImuSample* sample) {
  bool hasSample = false;
  portENTER_CRITICAL(&sampleBufferMux);
  if (bufferedSamples > 0) {
    *sample = sampleBuffer[sampleReadIndex];
    sampleReadIndex = (sampleReadIndex + 1) % SAMPLE_BUFFER_SIZE;
    bufferedSamples--;
    hasSample = true;
  }
  portEXIT_CRITICAL(&sampleBufferMux);
  return hasSample;
}

int formatSampleLine(const ImuSample& sample, char* dataBuffer, size_t dataBufferSize) {
  return snprintf(dataBuffer, dataBufferSize,
                  "%lu,%lu,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f\n",
                  (unsigned long)sample.index,
                  (unsigned long)sample.timeMs,
                  sample.accX, sample.accY, sample.accZ,
                  sample.gyrX, sample.gyrY, sample.gyrZ);
}

void transmitBufferedSamples(bool clientConnected) {
  char dataBuffer[160];

  while (true) {
    ImuSample sample;
    if (!popSample(&sample)) {
      break;
    }

    const int lineLength = formatSampleLine(sample, dataBuffer, sizeof(dataBuffer));
    if (lineLength <= 0 || lineLength >= (int)sizeof(dataBuffer)) {
      droppedBufferedSamples++;
      continue;
    }

    bool sent = false;
    if (clientConnected) {
      sent = (SerialBT.write((const uint8_t*)dataBuffer, lineLength) == (size_t)lineLength);
    }

    if (SEND_USB_SERIAL) {
      if (Serial.availableForWrite() < lineLength) {
        if (!sent) {
          break;
        }
      } else {
        Serial.write((const uint8_t*)dataBuffer, lineLength);
        sent = true;
      }
    }

    if (!sent) {
      break;
    }
  }
}

void sampleTask(void* parameter) {
  unsigned long nextSampleTime = millis();

  while (true) {
    const unsigned long currentTime = millis();
    if ((long)(currentTime - nextSampleTime) >= 0) {
      nextSampleTime += SAMPLE_INTERVAL;
      if ((long)(currentTime - nextSampleTime) >= (long)SAMPLE_INTERVAL) {
        nextSampleTime = currentTime;
      }

      if (M5.Imu.update()) {
        auto imuData = M5.Imu.getImuData();
        ImuSample sample;
        sample.index = ++sampleIndex;
        sample.timeMs = nextSampleTime;
        sample.accX = imuData.accel.x;
        sample.accY = imuData.accel.y;
        sample.accZ = imuData.accel.z;
        sample.gyrX = imuData.gyro.x;
        sample.gyrY = imuData.gyro.y;
        sample.gyrZ = imuData.gyro.z;

        if (SerialBT.hasClient() || SEND_USB_SERIAL) {
          pushSample(sample);
        }
      }
    }

    vTaskDelay(1);
  }
}
// 表示更新用
void drawStatus(bool connected) {
  M5.Display.fillScreen(BLACK);
  M5.Display.setTextColor(WHITE);
  M5.Display.setTextSize(2);
  M5.Display.setCursor(0, 0);
  M5.Display.println("BT Classic IMU");
  M5.Display.print("Name: ");
  M5.Display.println(btName);
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
  M5.Display.println("index,timeMs,");
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

  uint64_t chipId = ESP.getEfuseMac();
  snprintf(btName, sizeof(btName), "%s-%04X", BT_NAME_PREFIX, (uint16_t)(chipId & 0xFFFF));

  // Bluetooth Classic SPP 開始
  if (!SerialBT.begin(btName)) {
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
  Serial.println(btName);
  Serial.println("[BT] Pair/connect from PC or smartphone via Bluetooth SPP.");
  Serial.println("index,timeMs,accX,accY,accZ,gyrX,gyrY,gyrZ");
  drawStatus(false);
  xTaskCreatePinnedToCore(sampleTask, "imu_sample_task", 4096, NULL, 2, NULL, 1);
}
void loop() {
  M5.update();
  const bool clientConnected = SerialBT.hasClient();
  if (clientConnected != oldClientConnected) {
    clearSampleBuffer();
    drawStatus(clientConnected);
    oldClientConnected = clientConnected;
  }

  transmitBufferedSamples(clientConnected);
}
