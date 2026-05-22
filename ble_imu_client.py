#!/usr/bin/env python3
"""
M5Stack Core2 BLE IMU データ受信クライアント
加速度・ジャイロセンサーデータをBLE通信で受信するスクリプト
"""

import asyncio
import sys
from bleak import BleakClient, BleakScanner
import csv
from datetime import datetime

# BLE定義
SERVICE_UUID = "12345678-1234-1234-1234-123456789012"
CHARACTERISTIC_UUID = "87654321-4321-4321-4321-210987654321"
DEVICE_NAME = "M5Stack-Core2-IMU"

class IMUDataReceiver:
    def __init__(self, output_file=None):
        self.output_file = output_file
        self.csv_writer = None
        self.csv_file = None
        self.data_count = 0
        self.start_time = None
        
        if output_file:
            self.csv_file = open(output_file, 'w', newline='')
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(['Timestamp', 'AccX', 'AccY', 'AccZ', 'GyrX', 'GyrY', 'GyrZ'])
    
    def notification_handler(self, sender, data):
        """BLE通知受信時のコールバック"""
        try:
            # データをデコード
            message = data.decode('utf-8').strip()
            
            # 改行で分割（複数のセンサー読み取り値が含まれる可能性あり）
            for line in message.split('\n'):
                if not line:
                    continue
                
                # カンマで分割
                values = line.split(',')
                if len(values) != 6:
                    continue
                
                # 数値に変換
                acc_x, acc_y, acc_z, gyr_x, gyr_y, gyr_z = map(float, values)
                
                self.data_count += 1
                timestamp = datetime.now().isoformat()
                
                # 画面に表示
                print(f"[{self.data_count}] {timestamp} | "
                      f"Acc: ({acc_x:7.2f}, {acc_y:7.2f}, {acc_z:7.2f}) | "
                      f"Gyr: ({gyr_x:8.2f}, {gyr_y:8.2f}, {gyr_z:8.2f})")
                
                # CSVに保存
                if self.csv_writer:
                    self.csv_writer.writerow([timestamp, acc_x, acc_y, acc_z, gyr_x, gyr_y, gyr_z])
                    self.csv_file.flush()
        
        except Exception as e:
            print(f"Error processing data: {e}")
    
    def close(self):
        """ファイルをクローズ"""
        if self.csv_file:
            self.csv_file.close()
            print(f"\nData saved to: {self.output_file}")
            print(f"Total records: {self.data_count}")

async def find_device(device_name=DEVICE_NAME):
    """デバイスをスキャンして探す"""
    print(f"Scanning for device: {device_name}...")
    
    devices = await BleakScanner.discover()
    for device in devices:
        if device.name and device_name in device.name:
            print(f"Found device: {device.name} ({device.address})")
            return device
    
    print(f"Device {device_name} not found!")
    return None

async def main():
    """メイン処理"""
    # コマンドライン引数で出力ファイル名を指定可能
    output_file = None
    if len(sys.argv) > 1:
        output_file = sys.argv[1]
    else:
        # デフォルトファイル名
        output_file = f"imu_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    # デバイスを探す
    device = await find_device()
    if not device:
        return
    
    receiver = IMUDataReceiver(output_file)
    
    try:
        async with BleakClient(device.address) as client:
            print(f"Connected to {device.name}")
            print("Listening for IMU data... (Press Ctrl+C to stop)")
            print("-" * 100)
            
            # 通知を開始
            await client.start_notify(CHARACTERISTIC_UUID, receiver.notification_handler)
            
            # Ctrl+Cまで接続を維持
            try:
                while True:
                    await asyncio.sleep(0.1)
            except KeyboardInterrupt:
                print("\nStopping...")
                await client.stop_notify(CHARACTERISTIC_UUID)
    
    except Exception as e:
        print(f"Connection error: {e}")
    
    finally:
        receiver.close()

if __name__ == "__main__":
    # 非同期処理実行
    asyncio.run(main())
