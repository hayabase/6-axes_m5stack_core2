# M5Stack Core2 6軸IMU 送受信システム

M5Stack Core2 v1.3 の加速度・ジャイロセンサーを 100Hz で読み取り、PC 側へ送信する Arduino / Python コードです。

このリポジトリには、通信方式が異なる 2 種類の Arduino コードがあります。Bluetooth Classic 版は、M5側で生成したサンプル番号と時刻を含む `index,timeMs,accX,accY,accZ,gyrX,gyrY,gyrZ` の CSV を出力します。

この README では、Bluetooth Low Energy は正式名称の `BLE` と表記します。メモや会話中で `BLT` と書いている場合も、ここでは BLE のこととして整理しています。

## 対応コード

| 通信方式 | Arduinoコード | Pythonコード | 受信方法 | 備考 |
| --- | --- | --- | --- | --- |
| BLE (Bluetooth Low Energy) | `6axes_m5/6axes_m5.ino` | `ble_imu_client.py` | BLE Notify | CSV保存に対応 |
| BLE (Bluetooth Low Energy) | `6axes_m5/6axes_m5.ino` | `ble_sample_rate_monitor.py` | BLE Notify | 受信サンプリングレート確認用 |
| Bluetooth Classic | `6axes_m5_bluetooth_classic/6axes_m5_bluetooth_classic.ino` | `btclassic_sample_rate_monitor.py` | SPP仮想シリアル / COMポート | 受信サンプリングレート確認用 |
| Bluetooth Classic | `6axes_m5_bluetooth_classic/6axes_m5_bluetooth_classic.ino` | `btclassic_multi_imu_sample_rate_monitor.py` | SPP仮想シリアル / COMポート | 複数台の1秒ごとの受信サンプル数確認用 |

## BLE と Bluetooth Classic の違い

### BLE (Bluetooth Low Energy)

`6axes_m5/6axes_m5.ino` は BLE のサーバーとして動作し、IMU データを Notification で送信します。PC 側では `bleak` を使って BLE デバイスを探し、UUID を指定して通知を受信します。

- デバイス名: `M5Stack-Core2-IMU`
- サービスUUID: `12345678-1234-1234-1234-123456789012`
- キャラクタリスティックUUID: `87654321-4321-4321-4321-210987654321`
- COMポートとしては表示されません
- 環境や接続状態によって、受信が不安定になることがありました

BLE 側が不安定な場合は、`ble_sample_rate_monitor.py` で実際の受信レートを確認してください。受信が途切れる、100Hz 付近で安定しない、接続が切れる場合は Bluetooth Classic 版との比較を行います。

### Bluetooth Classic

`6axes_m5_bluetooth_classic/6axes_m5_bluetooth_classic.ino` は Bluetooth Classic SPP で動作します。PC 側ではペアリング後に仮想シリアルポートとして見えるため、COMポートを開いてデータを読みます。

- デバイス名: `M5Stack-IMU-XXXX`（`XXXX` はM5Stackごとの個体ID末尾4桁）
- 通信方式: Bluetooth Classic SPP
- PC側では COMポート / シリアルポートとして扱います
- `btclassic_sample_rate_monitor.py` はポート一覧を表示し、番号選択で接続します
- `btclassic_multi_imu_sample_rate_monitor.py` は最初に接続台数を入力し、IMUごとにポート番号を選んで接続します
- Arduino 側は Bluetooth Classic と USB Serial の両方に同じCSVを出力します
- 複数台を使う場合は、各M5Stackをこのスケッチで書き直してから、OS側で古い同名ペアリングを削除し、固有名でペアリングし直してください

## データ形式

Bluetooth Classic 版のArduinoから送信される1サンプルは次の形式です。

```text
index,timeMs,accX,accY,accZ,gyrX,gyrY,gyrZ
```

例:

```text
1234,56789,0.12,9.81,-0.05,1.23,-0.45,0.78
```

`index` はM5側のサンプル番号、`timeMs` はM5側の `millis()` 時刻です。Bluetooth受信タイミングの揺れと、M5側の生成レートを分けて確認するために使います。

## セットアップ

### Arduino側

1. Arduino IDE をインストールします。
2. Arduino IDE の `Preferences` -> `Additional Boards Manager URLs` に以下を追加します。

```text
https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/arduino/package_m5stack_index.json
```

3. Board Manager で `m5stack` を検索してインストールします。
4. Library Manager で `M5Core2` をインストールします。
5. ボードは `M5Stack-Core2` を選択します。
6. 使う通信方式に合わせてスケッチを開き、M5Stack Core2 にアップロードします。

BLE 版:

```text
6axes_m5/6axes_m5.ino
```

Bluetooth Classic 版:

```text
6axes_m5_bluetooth_classic/6axes_m5_bluetooth_classic.ino
```

### Python側

BLE 版を使う場合:

```bash
pip install bleak
```

Bluetooth Classic 版を使う場合:

```bash
pip install pyserial
```

## 使用方法

### BLEでCSV保存

M5Stack に `6axes_m5/6axes_m5.ino` を書き込んでから実行します。

```bash
python3 ble_imu_client.py
```

出力ファイル名を指定する場合:

```bash
python3 ble_imu_client.py sensor_data.csv
```

デフォルトでは `imu_data_YYYYMMDD_HHMMSS.csv` の形式で保存されます。

### BLEの受信サンプリングレート確認

```bash
python3 ble_sample_rate_monitor.py
```

表示更新間隔を変える場合:

```bash
python3 ble_sample_rate_monitor.py --interval 0.5
```

デバイス名を指定する場合:

```bash
python3 ble_sample_rate_monitor.py --device-name M5Stack-Core2-IMU
```

### Bluetooth Classicの受信サンプリングレート確認

M5Stack に `6axes_m5_bluetooth_classic/6axes_m5_bluetooth_classic.ino` を書き込み、PC 側で画面に表示された `M5Stack-IMU-XXXX` とペアリングしてから実行します。

```bash
python3 btclassic_sample_rate_monitor.py
```

実行すると利用可能なシリアルポートが一覧表示されます。使用する COMポート / シリアルポートの番号を入力してください。

ポートを直接指定する場合:

```bash
python3 btclassic_sample_rate_monitor.py --port COM5
```

macOS / Linux の例:

```bash
python3 btclassic_sample_rate_monitor.py --port /dev/tty.M5Stack-IMU-1234
```

macOSで `/dev/cu.*` を開いてもM5Stack側が `Waiting...` のままなら、同名の `/dev/tty.*` 側を試します。

```bash
python3 btclassic_sample_rate_monitor.py --use-tty
```

### Bluetooth Classicで複数台の受信サンプル数確認

各M5Stackに `6axes_m5_bluetooth_classic/6axes_m5_bluetooth_classic.ino` を書き込み、画面に表示された `M5Stack-IMU-XXXX` の名前でOS側からペアリングします。

```bash
python3 btclassic_multi_imu_sample_rate_monitor.py
```

実行後、最初に接続台数を入力し、続けて `IMU1`, `IMU2` の順にポート番号を選択します。出力は1秒ごとの受信サンプル数です。

```text
IMU1_samples_per_sec,IMU2_samples_per_sec
100,99
100,100
99,100
```

1秒ごとの生の受信数は、Bluetooth Classic SPP とOS側のバッファリングで `80 -> 120` のように揺れることがあります。平均として100Hz付近かを見たい場合は、直近5秒または10秒の移動平均Hzを表示します。

```bash
python3 btclassic_multi_imu_sample_rate_monitor.py --rate-window 10
```

```text
IMU1_rolling_hz_10s,IMU2_rolling_hz_10s
99.8,100.1
100.0,99.9
```

Bluetoothの受信バーストを避けてM5側の生成レートを見たい場合は、更新済みArduinoスケッチを書き込んだ上で `--source-rate` を使います。

```bash
python3 btclassic_multi_imu_sample_rate_monitor.py --source-rate --rate-window 10
```

```text
IMU1_source_hz_10s,IMU2_source_hz_10s
100.00,100.00
100.00,100.00
```

`0,0` が続き、M5Stack側の表示が `Waiting...` のままなら、Pythonがローカルのシリアルポートを開けているだけで、Bluetooth Classic SPP接続は成立していません。古い同名ペアリングを削除し、M5Stack画面に表示された固有名でペアリングし直してください。

更新後もmacOSのポート一覧に `M5Stack-Core2-IMU`, `M5Stack-Core2-IMU_1`, `M5Stack-Core2-IMU_2` だけが出ている場合は、古いペアリング情報を見ています。`M5Stack-IMU-XXXX` の名前が見える状態まで、OS側のペアリング削除と再ペアリングを行ってください。

## サンプリングレート確認ツールの出力例

```text
[10:30:46] 1秒:  100 samples ( 100.0 Hz) | 直近10秒:   100 samples ( 100.0 Hz) | 合計:     100 | 平均:  100.0 Hz | 経過:    1.0s | 無効行: 0
[10:30:55] 1秒:  100 samples ( 100.0 Hz) | 直近10秒:  1000 samples ( 100.0 Hz) | 合計:    1000 | 平均:  100.0 Hz | 経過:   10.0s | 無効行: 0
```

## トラブルシューティング

### BLEでデバイスが見つからない場合

- M5Stack の画面に `BLE IMU Server` が表示されているか確認します。
- PC の Bluetooth を一度オフ/オンします。
- `ble_sample_rate_monitor.py --device-name M5Stack-Core2-IMU` でデバイス名が合っているか確認します。
- BLE は COMポートには出てこないため、シリアルモニタからは読めません。

### BLEの受信が不安定な場合

- `ble_sample_rate_monitor.py` で 1秒ごとの受信サンプル数を確認します。
- 100Hz 付近で安定しない場合は、Bluetooth Classic 版の `btclassic_sample_rate_monitor.py` でも同じ条件で確認します。
- PC の Bluetooth アダプタ、OS、周囲の無線環境によって安定性が変わることがあります。

### Bluetooth Classicでポートが出ない場合

- OS の Bluetooth 設定で、M5Stack画面に表示された `M5Stack-IMU-XXXX` とペアリングします。
- ペアリング後に仮想 COMポート / シリアルポートが作成されているか確認します。
- Windows ではデバイスマネージャーの `ポート (COM と LPT)` を確認します。
- macOS / Linux では `/dev/tty.*` や `/dev/rfcomm*` を確認します。

### WindowsのBluetooth Classicで受信が欠落する場合

Bluetooth Classic は Windows では COMポートとして扱われるため、受信データが欠落する場合は COMポート側のバッファ設定も確認します。Windows のデバイスマネージャーで対象の COMポートを開き、詳細設定から受信バッファを小さめに設定して試してください。

参考: [WindowsのRS-232Cシリアル通信で受信データに欠落が発生する](https://gabekore.org/windows-rs232c-deficit-recv-data)

### Pythonで依存ライブラリがないと言われる場合

BLE:

```bash
pip install bleak
```

Bluetooth Classic:

```bash
pip install pyserial
```

### M5Stack側でIMUが初期化されない場合

- M5Core2 ライブラリが Core2 に対応しているか確認します。
- Arduino IDE のボード設定が `M5Stack-Core2` になっているか確認します。
- USB接続後に再起動してから再度アップロードします。

## 注意事項

- Python 側のタイムスタンプや受信レートは、PC 側で受信できたタイミングをもとにしています。
- Arduino 側は 10ms 間隔でサンプリングする実装ですが、無線通信やOS側の処理によりPC側の受信間隔は揺れることがあります。
- BLE 版と Bluetooth Classic 版で、送信する CSV の列順は同じです。
- この環境では Arduino のコンパイル確認は未実施です。

## 参考資料

- [M5Stack Core2 ドキュメント](https://docs.m5stack.com/en/core/core2)
- [ESP32 BLE Arduino](https://github.com/espressif/arduino-esp32/blob/master/libraries/BLE/)
- [Arduino ESP32 BluetoothSerial](https://github.com/espressif/arduino-esp32/tree/master/libraries/BluetoothSerial)
- [Bleak ドキュメント](https://bleak.readthedocs.io/)
- [pySerial ドキュメント](https://pyserial.readthedocs.io/)
- [WindowsのRS-232Cシリアル通信で受信データに欠落が発生する](https://gabekore.org/windows-rs232c-deficit-recv-data)
