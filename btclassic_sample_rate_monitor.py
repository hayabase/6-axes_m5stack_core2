#!/usr/bin/env python3
"""
M5Stack Core2 Bluetooth Classic IMU 受信サンプリングレート確認ツール

Bluetooth Classic SPP の仮想シリアルポートから読み取り、直近1秒間と
直近10秒間に受信した有効サンプル数を継続表示します。
"""

import argparse
import os
import sys
from collections import deque
from datetime import datetime
from time import perf_counter, sleep


DEFAULT_BAUDRATE = 115200
DEFAULT_INTERVAL_SECONDS = 1.0
DEFAULT_TIMEOUT_SECONDS = 0.1
DEFAULT_DIAGNOSTICS_SECONDS = 5.0


class SampleRateMonitor:
    def __init__(self, window_seconds=10.0):
        self.window_seconds = window_seconds
        self.sample_timestamps = deque()
        self.total_samples = 0
        self.invalid_lines = 0
        self.received_lines = 0
        self.raw_bytes = 0
        self.last_line_preview = ""
        self.first_sample_time = None

    def process_raw_line(self, raw_line):
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
            return

        self.received_lines += 1
        self.raw_bytes += len(raw_line)
        self.last_line_preview = line[:120]
        self._process_line(line)

    def _process_line(self, line):
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

        now = perf_counter()
        if self.first_sample_time is None:
            self.first_sample_time = now

        self.total_samples += 1
        self.sample_timestamps.append(now)

    def diagnostics(self):
        return (
            f"bytes={self.raw_bytes}, "
            f"lines={self.received_lines}, "
            f"valid={self.total_samples}, "
            f"invalid={self.invalid_lines}"
        )

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
        elapsed = now - self.first_sample_time if self.first_sample_time else 0.0
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


def macos_tty_counterpart(port):
    if not port.startswith("/dev/cu."):
        return None

    tty_port = "/dev/tty." + port[len("/dev/cu.") :]
    if os.path.exists(tty_port):
        return tty_port

    return None


def print_no_sample_diagnostics(port, monitor):
    print(
        f"[diagnostic] まだ有効な6値CSVサンプルを受信できていません: "
        f"{monitor.diagnostics()}",
        file=sys.stderr,
        flush=True,
    )

    if monitor.raw_bytes == 0:
        print(
            "[diagnostic] bytes=0 なので、Pythonはポートを開けていますが、"
            "M5Stack側のBluetooth Classic SPP接続は成立していない可能性が高いです。",
            file=sys.stderr,
            flush=True,
        )
        print(
            "[diagnostic] M5Stack画面が Connected になっているか、"
            "選択したポートが対象IMUのSPPポートか、同じBT名の古いペアリングが残っていないかを確認してください。",
            file=sys.stderr,
            flush=True,
        )

        tty_port = macos_tty_counterpart(port)
        if tty_port:
            print(
                f"[diagnostic] macOSでは同名のttyポートで読める場合があります: {tty_port}",
                file=sys.stderr,
                flush=True,
            )
    elif monitor.invalid_lines and monitor.last_line_preview:
        print(
            f"[diagnostic] 最後の無効行候補: {monitor.last_line_preview!r}",
            file=sys.stderr,
            flush=True,
        )


def monitor_sample_rate(
    port,
    baudrate,
    interval_seconds,
    timeout_seconds,
    diagnostics_seconds,
    use_tty,
):
    serial, list_ports = import_serial_modules()
    if serial is None:
        return 1

    if interval_seconds <= 0:
        print("表示更新間隔は0より大きい値を指定してください。")
        return 1

    if diagnostics_seconds <= 0:
        print("診断表示間隔は0より大きい値を指定してください。")
        return 1

    if port is None:
        port = select_port_from_list(list_ports)
        if port is None:
            return 1

    if use_tty:
        tty_port = macos_tty_counterpart(port)
        if tty_port:
            print(f"Using tty counterpart: {port} -> {tty_port}")
            port = tty_port

    monitor = SampleRateMonitor()

    try:
        with serial.Serial(port, baudrate=baudrate, timeout=timeout_seconds) as serial_port:
            print(f"Opened serial port {port} ({baudrate} bps)")
            print("Bluetooth Classic IMU の受信サンプリングレートを確認中... (Ctrl+Cで停止)")
            print("-" * 110)

            serial_port.reset_input_buffer()
            next_print_time = perf_counter() + interval_seconds
            next_diagnostics_time = perf_counter() + diagnostics_seconds

            while True:
                raw_line = serial_port.readline()
                if raw_line:
                    monitor.process_raw_line(raw_line)
                else:
                    sleep(0.001)

                now = perf_counter()
                if now >= next_print_time:
                    monitor.print_status()
                    next_print_time += interval_seconds

                    if monitor.total_samples == 0 and now >= next_diagnostics_time:
                        print_no_sample_diagnostics(port, monitor)
                        next_diagnostics_time = now + diagnostics_seconds

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
    parser.add_argument(
        "--diagnostics",
        type=float,
        default=DEFAULT_DIAGNOSTICS_SECONDS,
        help=(
            "有効サンプルが0のときに標準エラーへ診断を出す間隔（秒）。"
            f"デフォルト: {DEFAULT_DIAGNOSTICS_SECONDS}"
        ),
    )
    parser.add_argument(
        "--use-tty",
        action="store_true",
        help=(
            "macOSで /dev/cu.* の代わりに同名の /dev/tty.* があれば使用します。"
            "番号選択は通常どおり行えます。"
        ),
    )
    return parser.parse_args()


def main():
    args = parse_args()
    return monitor_sample_rate(
        port=args.port,
        baudrate=args.baudrate,
        interval_seconds=args.interval,
        timeout_seconds=args.timeout,
        diagnostics_seconds=args.diagnostics,
        use_tty=args.use_tty,
    )


if __name__ == "__main__":
    raise SystemExit(main())
