#!/usr/bin/env python3
"""
M5Stack Core2 Bluetooth Classic IMU 受信サンプリングレート確認ツール

Bluetooth Classic SPP の仮想シリアルポートから読み取り、直近1秒間と
直近10秒間に受信した有効サンプル数を継続表示します。
"""

import argparse
from collections import deque
from datetime import datetime
from time import perf_counter, sleep


DEFAULT_BAUDRATE = 115200
DEFAULT_INTERVAL_SECONDS = 1.0
DEFAULT_TIMEOUT_SECONDS = 0.1


class SampleRateMonitor:
    def __init__(self, window_seconds=10.0):
        self.window_seconds = window_seconds
        self.sample_timestamps = deque()
        self.total_samples = 0
        self.invalid_lines = 0
        self.start_time = perf_counter()

    def process_line(self, line):
        """1行のCSVが6軸IMUデータとして有効ならサンプルとして数える。"""
        values = line.strip().split(",")
        if len(values) != 6:
            self.invalid_lines += 1
            return

        try:
            [float(value) for value in values]
        except ValueError:
            self.invalid_lines += 1
            return

        self.total_samples += 1
        self.sample_timestamps.append(perf_counter())

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


def import_serial_modules():
    try:
        import serial
        from serial.tools import list_ports
    except ModuleNotFoundError:
        print("Missing Python dependency: pyserial")
        print("Install it with: pip install pyserial")
        return None, None

    return serial, list_ports


def format_port_info(port_info):
    details = [port_info.device]
    if port_info.description:
        details.append(port_info.description)
    if port_info.hwid:
        details.append(port_info.hwid)
    return " | ".join(details)


def select_port_from_list(list_ports):
    ports = sorted(list_ports.comports(), key=lambda port: port.device)

    if not ports:
        print("利用可能なシリアルポートが見つかりません。")
        print("M5Stack Core2 と Bluetooth Classic でペアリング済みか確認してください。")
        return None

    print("利用可能なシリアルポート:")
    for index, port_info in enumerate(ports, start=1):
        print(f"  [{index}] {format_port_info(port_info)}")

    while True:
        choice = input("使用するポート番号を入力してください: ").strip()

        try:
            port_number = int(choice)
        except ValueError:
            print("番号で入力してください。")
            continue

        if 1 <= port_number <= len(ports):
            return ports[port_number - 1].device

        print(f"1 から {len(ports)} までの番号を入力してください。")


def monitor_sample_rate(port, baudrate, interval_seconds, timeout_seconds):
    serial, list_ports = import_serial_modules()
    if serial is None:
        return 1

    if port is None:
        port = select_port_from_list(list_ports)
        if port is None:
            return 1

    monitor = SampleRateMonitor()

    try:
        with serial.Serial(port, baudrate=baudrate, timeout=timeout_seconds) as serial_port:
            print(f"Connected to {port} ({baudrate} bps)")
            print("Bluetooth Classic IMU の受信サンプリングレートを確認中... (Ctrl+Cで停止)")
            print("-" * 110)

            serial_port.reset_input_buffer()
            next_print_time = perf_counter() + interval_seconds

            while True:
                raw_line = serial_port.readline()
                if raw_line:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if line:
                        monitor.process_line(line)
                else:
                    sleep(0.001)

                now = perf_counter()
                if now >= next_print_time:
                    monitor.print_status()
                    next_print_time += interval_seconds

    except KeyboardInterrupt:
        print("\nStopping...")
        return 0
    except serial.SerialException as error:
        print(f"Serial connection error: {error}")
        return 1


def parse_args():
    parser = argparse.ArgumentParser(
        description="M5Stack Core2 Bluetooth Classic IMUの受信サンプリングレートを確認します。"
    )
    parser.add_argument(
        "--port",
        help="使用するシリアルポート。未指定の場合は一覧から番号で選択します。",
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=DEFAULT_BAUDRATE,
        help=f"シリアルのボーレート。デフォルト: {DEFAULT_BAUDRATE}",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL_SECONDS,
        help=f"表示更新間隔（秒）。デフォルト: {DEFAULT_INTERVAL_SECONDS}",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"シリアル読み取りタイムアウト（秒）。デフォルト: {DEFAULT_TIMEOUT_SECONDS}",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    return monitor_sample_rate(
        port=args.port,
        baudrate=args.baudrate,
        interval_seconds=args.interval,
        timeout_seconds=args.timeout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
