# M5Stack Core2 BLE IMU 送受信システム

M5Stack Core2 v1.3の加速度・ジャイロセンサーをBLE（Bluetooth Low Energy）で100Hzのサンプリングレートで送受信するシステムです。

## 概要

### Arduino側（送信）
- M5Stack Core2 v1.3のIMUセンサー（MPU6886）から加速度とジャイロデータを読み込み
- 100Hzのサンプリングレート（10ms間隔）で取得
- BLE通知経由でデータを送信
- データ形式：`accX,accY,accZ,gyrX,gyrY,gyrZ\n`

### Python側（受信）
- BLEクライアントとしてM5StackのBLEサーバーに接続
- リアルタイムで加速度・ジャイロデータを受信
- CSVファイルに記録

## セットアップ

### Arduino側

1. **Arduino IDEのインストール**
   - [Arduino IDE](https://www.arduino.cc/en/software)をインストール

2. **M5Stack Board Packageのインストール**
   - Arduino IDE → Preferences → Additional Boards Manager URLs に以下を追加：
     ```
     https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/arduino/package_m5stack_index.json
     ```
   - Board Manager（Ctrl+Shift+B）で「m5stack」を検索・インストール

3. **ライブラリのインストール**
   - Arduino IDE → Library Manager（Ctrl+Shift+I）で以下をインストール：
     - M5Core2
     - BLEDevice
     - BluetoothSerial
   
4. **ボード設定**
   - Board: "M5Stack-Core2"
   - Port: 接続しているUSBポート

5. **スケッチのアップロード**
   - `6axes_m5/6axes_m5.ino`をArduino IDEで開く
   - 右上の「→」ボタンでアップロード

### Python側

1. **Python 3.8以上のインストール**

2. **必要なパッケージのインストール**
   ```bash
   pip install bleak
   ```

3. **Bluetooth権限設定（Linuxの場合）**
   ```bash
   sudo setcap cap_net_raw,cap_net_admin+ep $(eval readlink -f `which python3`)
   ```

## 使用方法

### Arduino（M5Stack）側
1. M5StackをUSBで接続
2. Arduino IDEでスケッチをアップロード
3. M5Stackの画面に「BLE IMU Server」が表示される
4. クライアント接続待機中

### Python側

基本的な使用方法：
```bash
python3 ble_imu_client.py [出力ファイル名]
```

例：
```bash
# デフォルト名で保存（imu_data_YYYYMMDD_HHMMSS.csv）
python3 ble_imu_client.py

# カスタムファイル名で保存
python3 ble_imu_client.py sensor_data.csv
```

受信サンプリングレートの確認：
```bash
python3 ble_sample_rate_monitor.py
```

この確認ツールはCSV保存を行わず、BLE通知で届いた有効なIMUデータ行だけを数えます。実行中は1秒ごとに、直近1秒間の受信サンプル数と直近10秒間の受信サンプル数を表示します。

表示更新間隔を変更する場合：
```bash
python3 ble_sample_rate_monitor.py --interval 0.5
```

デバイス名を指定する場合：
```bash
python3 ble_sample_rate_monitor.py --device-name M5Stack-Core2-IMU
```

### 出力例

コンソール出力：
```
Scanning for device: M5Stack-Core2-IMU...
Found device: M5Stack-Core2-IMU (xx:xx:xx:xx:xx:xx)
Connected to M5Stack-Core2-IMU
Listening for IMU data... (Press Ctrl+C to stop)
----------------------------------------------------------------------------------------------------
[1] 2024-01-15T10:30:45.123456 | Acc: (  0.12,   9.81,  -0.05) | Gyr: (   1.23,  -0.45,   0.78)
[2] 2024-01-15T10:30:45.133456 | Acc: (  0.13,   9.82,  -0.04) | Gyr: (   1.22,  -0.46,   0.79)
...
```

CSV出力例（imu_data_YYYYMMDD_HHMMSS.csv）：
```
Timestamp,AccX,AccY,AccZ,GyrX,GyrY,GyrZ
2024-01-15T10:30:45.123456,0.12,9.81,-0.05,1.23,-0.45,0.78
2024-01-15T10:30:45.133456,0.13,9.82,-0.04,1.22,-0.46,0.79
...
```

サンプリングレート確認ツールの出力例：
```
Scanning for device: M5Stack-Core2-IMU...
Found device: M5Stack-Core2-IMU (xx:xx:xx:xx:xx:xx)
Connected to M5Stack-Core2-IMU
受信サンプリングレートを確認中... (Ctrl+Cで停止)
--------------------------------------------------------------------------------------------------------------
[10:30:46] 1秒:  100 samples ( 100.0 Hz) | 直近10秒:   100 samples ( 100.0 Hz) | 合計:     100 | 平均:  100.0 Hz | 経過:    1.0s | 無効行: 0
[10:30:55] 1秒:  100 samples ( 100.0 Hz) | 直近10秒:  1000 samples ( 100.0 Hz) | 合計:    1000 | 平均:  100.0 Hz | 経過:   10.0s | 無効行: 0
```

## BLE通信仕様

- **サービスUUID**: `12345678-1234-1234-1234-123456789012`
- **キャラクタリスティックUUID**: `87654321-4321-4321-4321-210987654321`
- **通信方式**: Notification（サーバーから通知）
- **サンプリングレート**: 100Hz（10ms間隔）

## トラブルシューティング

### Pythonでデバイスが見つからない場合

**macOS:**
```bash
# Bluetoothの再起動
sudo launchctl stop com.apple.blued
sudo launchctl start com.apple.blued
```

**Linux:**
```bash
# bluetoothctlで確認
bluetoothctl
scan on
```

**Windows:**
- Bluetoothデバイスの接続確認
- ドライバの更新

### Python実行時にPermission Deniedが出る場合（Linux）
```bash
sudo setcap cap_net_raw,cap_net_admin+ep /usr/bin/python3
```

### M5Stack側でIMUが初期化されない場合
- M5CoreのバージョンがCore2に対応しているか確認
- I2Cアドレスが正しいか確認（MPU6886は0x68）

## 注意事項

- **クロック精度**: Pythonのタイムスタンプはクライアント側のシステム時刻です
- **データレート**: BLE MTU（最大転送ユニット）による制限あり
- **電力消費**: BLE送信により電力消費が増加します

## 参考資料

- [M5Stack Core2 ドキュメント](https://docs.m5stack.com/en/core/core2)
- [ESP32 BLE Arduino](https://github.com/espressif/arduino-esp32/blob/master/libraries/BLE/)
- [Bleak ドキュメント](https://bleak.readthedocs.io/)
# 6-axes_m5stack_core2
