#include <M5Core2.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
// #include <MPU6886.h>

// BLE関連の定義
#define SERVICE_UUID        "12345678-1234-1234-1234-123456789012"
#define CHARACTERISTIC_UUID "87654321-4321-4321-4321-210987654321"

BLEServer* pServer = NULL;
BLECharacteristic* pCharacteristic = NULL;
bool deviceConnected = false;
bool oldDeviceConnected = false;

// センサーデータ
float accX, accY, accZ;
float gyrX, gyrY, gyrZ;

// サンプリング用
unsigned long lastSampleTime = 0;
const unsigned long SAMPLE_INTERVAL = 10; // 100Hz = 10ms

// BLEサーバーコールバック
class MyServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
      deviceConnected = true;
    };
    
    void onDisconnect(BLEServer* pServer) {
      deviceConnected = false;
    }
};

void setup() {
  // M5Core2初期化
  M5.begin();
  
  // IMU初期化
  M5.IMU.Init();
  
  // シリアル通信初期化（デバッグ用）
  Serial.begin(115200);
  delay(100);
  
  // BLEデバイス初期化
  BLEDevice::init("M5Stack-Core2-IMU");
  
  // BLEサーバー作成
  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());
  
  // BLEサービス作成
  BLEService *pService = pServer->createService(SERVICE_UUID);
  
  // BLEキャラクタリスティック作成（通知対応）
  pCharacteristic = pService->createCharacteristic(
                      CHARACTERISTIC_UUID,
                      BLECharacteristic::PROPERTY_NOTIFY |
                      BLECharacteristic::PROPERTY_READ
                    );
  
  // キャラクタリスティックにディスクリプター追加
  pCharacteristic->addDescriptor(new BLE2902());
  
  // サービス開始
  pService->start();
  
  // アドバタイジング開始
  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setScanResponse(true);
  pAdvertising->setMinPreferred(0x06);
  pAdvertising->setMinPreferred(0x12);
  BLEDevice::startAdvertising();
  
  // 画面表示
  M5.Lcd.fillScreen(BLACK);
  M5.Lcd.setTextColor(WHITE);
  M5.Lcd.setTextSize(2);
  M5.Lcd.setCursor(0, 0);
  M5.Lcd.println("BLE IMU Server");
  M5.Lcd.println("Waiting for connection...");
  
  lastSampleTime = millis();
}

void loop() {
  unsigned long currentTime = millis();
  
  // 接続状態の変化を検出（自動的に再アドバタイジング）
  if (!deviceConnected && oldDeviceConnected) {
    delay(500);
    pServer->startAdvertising();
    oldDeviceConnected = deviceConnected;
  }
  
  if (deviceConnected && !oldDeviceConnected) {
    oldDeviceConnected = deviceConnected;
  }
  
  // 100Hz (10ms間隔) でサンプリング
  if (currentTime - lastSampleTime >= SAMPLE_INTERVAL) {
    lastSampleTime = currentTime;
    
    // センサーデータ読み込み
    M5.IMU.getAccelData(&accX, &accY, &accZ);
    M5.IMU.getGyroData(&gyrX, &gyrY, &gyrZ);
    
    // データフォーマット: "accX,accY,accZ,gyrX,gyrY,gyrZ\n"
    char dataBuffer[128];
    snprintf(dataBuffer, sizeof(dataBuffer), 
             "%.2f,%.2f,%.2f,%.2f,%.2f,%.2f\n",
             accX, accY, accZ, gyrX, gyrY, gyrZ);
    
    // BLEで送信
    if (deviceConnected) {
      pCharacteristic->setValue(dataBuffer);
      pCharacteristic->notify();
    }
    
    // シリアルモニタにも出力（デバッグ）
    Serial.print(dataBuffer);
  }
  
  M5.update();
}
