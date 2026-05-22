#!/usr/bin/env python3
"""
M5Stack Core2 BLE IMU 受信サンプリングレート確認ツール

直近1秒間と直近10秒間に受信した有効サンプル数を継続表示します。
"""

import argparse
import asyncio
from collections import deque
from datetime import datetime
from time import perf_counter

# BLE定義（ble_imu_client.py / 6axes_m5.ino と同じ値）
SERVICE_UUID = "12345678-1234-1234-1234-123456789012"
CHARACTERISTIC_UUID = "87654321-4321-4321-4321-210987654321"
DEVICE_NAME = "M5Stack-Core2-IMU"


class SampleRateMonitor:
    def __init__(self, window_seconds=10.0):
        self.window_seconds = window_seconds
        self.sample_timestamps = deque()
        self.total_samples = 0
        self.invalid_lines = 0
        self.start_time = perf_counter()

    def notification_handler(self, sender, data):
        """BLE通知に含まれる有効なIMUサンプル行を数える。"""
        now = perf_counter()

        try:
            message = data.decode("utf-8").strip()
        except UnicodeDecodeError:
            self.invalid_lines += 1
            return

        for line in message.splitlines():
            if not line:
                continue

            values = line.split(",")
            if len(values) != 6:
                self.invalid_lines += 1
                continue

            try:
                [float(value) for value in values]
            except ValueError:
                self.invalid_lines += 1
                continue

            self.total_samples += 1
            self.sample_timestamps.append(now)

    def _drop_old_samples(self, now):
        cutoff = now - self.window_seconds
        while self.sample_timestamps and self.sample_timestamps[0] < cutoff:
            self.sample_timestamps.popleft()

    def current_counts(self):
        now = perf_counter()
        self._drop_old_samples(now)

        one_second_cutoff = now - 1.0
        one_second_count = sum(
            1 for timestamp in self.sample_timestamps if timestamp >= one_second_cutoff
        )
        ten_second_count = len(self.sample_timestamps)
        elapsed = now - self.start_time
        average_hz = self.total_samples / elapsed if elapsed > 0 else 0.0

        return one_second_count, ten_second_count, elapsed, average_hz

    def print_status(self):
        one_second_count, ten_second_count, elapsed, average_hz = self.current_counts()
        timestamp = datetime.now().strftime("%H:%M:%S")
        ten_second_duration = min(elapsed, self.window_seconds)
        ten_second_hz = (
            ten_second_count / ten_second_duration if ten_second_duration > 0 else 0.0
        )

        print(
            f"[{timestamp}] "
            f"1秒: {one_second_count:4d} samples ({one_second_count:6.1f} Hz) | "
            f"直近10秒: {ten_second_count:5d} samples ({ten_second_hz:6.1f} Hz) | "
            f"合計: {self.total_samples:7d} | "
            f"平均: {average_hz:6.1f} Hz | "
            f"経過: {elapsed:6.1f}s | "
            f"無効行: {self.invalid_lines}"
        )


async def find_device(scanner, device_name=DEVICE_NAME):
    """デバイスをスキャンして探す。"""
    print(f"Scanning for device: {device_name}...")

    devices = await scanner.discover()
    for device in devices:
        if device.name and device_name in device.name:
            print(f"Found device: {device.name} ({device.address})")
            return device

    print(f"Device {device_name} not found!")
    return None


async def monitor_sample_rate(device_name=DEVICE_NAME, interval_seconds=1.0):
    try:
        from bleak import BleakClient, BleakScanner
    except ModuleNotFoundError:
        print("Missing Python dependency: bleak")
        print("Install it with: pip install bleak")
        return 1

    device = await find_device(BleakScanner, device_name)
    if not device:
        return 1

    monitor = SampleRateMonitor()

    try:
        async with BleakClient(device.address) as client:
            print(f"Connected to {device.name}")
            print("受信サンプリングレートを確認中... (Ctrl+Cで停止)")
            print("-" * 110)

            await client.start_notify(CHARACTERISTIC_UUID, monitor.notification_handler)

            try:
                while True:
                    await asyncio.sleep(interval_seconds)
                    monitor.print_status()
            except KeyboardInterrupt:
                print("\nStopping...")
            finally:
                await client.stop_notify(CHARACTERISTIC_UUID)

    except Exception as error:
        print(f"Connection error: {error}")
        return 1

    return 0


def parse_args():
    parser = argparse.ArgumentParser(
        description="M5Stack Core2 BLE IMUの受信サンプリングレートを確認します。"
    )
    parser.add_argument(
        "--device-name",
        default=DEVICE_NAME,
        help=f"検索するBLEデバイス名。デフォルト: {DEVICE_NAME}",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="表示更新間隔（秒）。デフォルト: 1.0",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    return await monitor_sample_rate(args.device_name, args.interval)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
