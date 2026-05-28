#!/usr/bin/env python3
"""
M5Stack Core2 Bluetooth Classic 複数IMU 受信サンプル数モニタ

Bluetooth Classic SPP の仮想シリアルポートを複数開き、各IMUから
直近1秒間に受信した有効サンプル数をCSV形式で継続表示します。
"""

import argparse
import os
import sys
import threading
from collections import deque
from time import perf_counter, sleep


DEFAULT_BAUDRATE = 115200
DEFAULT_INTERVAL_SECONDS = 1.0
DEFAULT_TIMEOUT_SECONDS = 0.1
DEFAULT_DIAGNOSTICS_SECONDS = 5.0
DEFAULT_RATE_WINDOW_SECONDS = 1.0


class SampleCounter:
    def __init__(self):
        self._lock = threading.Lock()
        self.total_samples = 0
        self.invalid_lines = 0
        self.received_lines = 0
        self.raw_bytes = 0
        self.last_line_preview = ""
        self.sample_timestamps = deque()
        self.source_samples = deque()
        self.source_rows = 0

    def process_raw_line(self, raw_line):
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
            return

        with self._lock:
            self.received_lines += 1
            self.raw_bytes += len(raw_line)
            self.last_line_preview = line[:120]

        self._process_line(line)

    def _process_line(self, line):
        """6値または index,timeMs付き8値のIMU CSVをサンプルとして数える。"""
        values = line.strip().split(",")
        if len(values) not in (6, 8):
            self._add_invalid_line()
            return

        try:
            if len(values) == 8:
                sample_index = int(values[0])
                sample_time_ms = float(values[1])
                [float(value) for value in values[2:]]
            else:
                sample_index = None
                sample_time_ms = None
                [float(value) for value in values]
        except ValueError:
            self._add_invalid_line()
            return

        with self._lock:
            self.total_samples += 1
            self.sample_timestamps.append(perf_counter())
            if sample_index is not None and sample_time_ms is not None:
                self.source_rows += 1
                self.source_samples.append((sample_index, sample_time_ms))

    def _add_invalid_line(self):
        with self._lock:
            self.invalid_lines += 1

    def snapshot(self, now=None, rate_window_seconds=None):
        with self._lock:
            window_count = None
            source_hz = None
            if now is not None and rate_window_seconds is not None:
                cutoff = now - rate_window_seconds
                while self.sample_timestamps and self.sample_timestamps[0] < cutoff:
                    self.sample_timestamps.popleft()
                window_count = len(self.sample_timestamps)

                if self.source_samples:
                    latest_source_time_ms = self.source_samples[-1][1]
                    source_cutoff_ms = latest_source_time_ms - (rate_window_seconds * 1000.0)
                    while (
                        len(self.source_samples) > 1
                        and self.source_samples[0][1] < source_cutoff_ms
                    ):
                        self.source_samples.popleft()

                    first_index, first_time_ms = self.source_samples[0]
                    last_index, last_time_ms = self.source_samples[-1]
                    source_elapsed_seconds = (last_time_ms - first_time_ms) / 1000.0
                    if source_elapsed_seconds > 0:
                        source_hz = (last_index - first_index) / source_elapsed_seconds

            return {
                "total_samples": self.total_samples,
                "invalid_lines": self.invalid_lines,
                "received_lines": self.received_lines,
                "raw_bytes": self.raw_bytes,
                "last_line_preview": self.last_line_preview,
                "window_count": window_count,
                "source_rows": self.source_rows,
                "source_hz": source_hz,
            }


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


def read_positive_int(prompt):
    while True:
        choice = input(prompt).strip()

        try:
            value = int(choice)
        except ValueError:
            print("番号で入力してください。")
            continue

        if value >= 1:
            return value

        print("1以上の数字を入力してください。")


def select_connection_count():
    return read_positive_int("接続するIMU台数を入力してください: ")


def macos_tty_counterpart(port):
    if not port.startswith("/dev/cu."):
        return None

    tty_port = "/dev/tty." + port[len("/dev/cu.") :]
    if os.path.exists(tty_port):
        return tty_port

    return None


def convert_to_macos_tty_ports(ports):
    converted_ports = []
    for port in ports:
        converted_ports.append(macos_tty_counterpart(port) or port)

    return converted_ports


def select_ports_from_list(list_ports, imu_count):
    ports = sorted(list_ports.comports(), key=lambda port: port.device)

    if not ports:
        print("利用可能なシリアルポートが見つかりません。")
        print("M5Stack Core2 と Bluetooth Classic でペアリング済みか確認してください。")
        return None

    if imu_count > len(ports):
        print(
            f"接続台数 {imu_count} 台に対して、利用可能なポートが {len(ports)} 個しかありません。"
        )
        return None

    print("利用可能なシリアルポート:")
    for index, port_info in enumerate(ports, start=1):
        print(f"  [{index}] {format_port_info(port_info)}")

    selected_ports = []
    selected_numbers = set()

    for imu_index in range(1, imu_count + 1):
        while True:
            choice = input(f"IMU{imu_index}で使用するポート番号を入力してください: ").strip()

            try:
                port_number = int(choice)
            except ValueError:
                print("番号で入力してください。")
                continue

            if not 1 <= port_number <= len(ports):
                print(f"1 から {len(ports)} までの番号を入力してください。")
                continue

            if port_number in selected_numbers:
                print("そのポートはすでに選択済みです。別の番号を選んでください。")
                continue

            selected_numbers.add(port_number)
            selected_ports.append(ports[port_number - 1].device)
            break

    return selected_ports


def read_serial_lines(imu_name, serial_port, counter, stop_event, errors):
    while not stop_event.is_set():
        try:
            raw_line = serial_port.readline()
        except Exception as error:  # pyserial may raise SerialException here.
            errors.append((imu_name, error))
            stop_event.set()
            return

        if raw_line:
            counter.process_raw_line(raw_line)
        else:
            sleep(0.001)


def print_stream_header(imu_count, rate_window_seconds, source_rate):
    if source_rate:
        window_label = f"{rate_window_seconds:g}s"
        columns = [
            f"IMU{index}_source_hz_{window_label}" for index in range(1, imu_count + 1)
        ]
    elif rate_window_seconds <= DEFAULT_RATE_WINDOW_SECONDS:
        columns = [f"IMU{index}_samples_per_sec" for index in range(1, imu_count + 1)]
    else:
        window_label = f"{rate_window_seconds:g}s"
        columns = [
            f"IMU{index}_rolling_hz_{window_label}" for index in range(1, imu_count + 1)
        ]
    print(",".join(columns), flush=True)


def format_diagnostics(port_labels, snapshots):
    chunks = []
    for index, (port, snapshot) in enumerate(zip(port_labels, snapshots), start=1):
        chunks.append(
            f"IMU{index}({port}): "
            f"bytes={snapshot['raw_bytes']}, "
            f"lines={snapshot['received_lines']}, "
            f"valid={snapshot['total_samples']}, "
            f"invalid={snapshot['invalid_lines']}"
        )

    return " | ".join(chunks)


def print_no_sample_diagnostics(port_labels, snapshots):
    print(
        "[diagnostic] まだ有効な6値CSVサンプルを受信できていません: "
        + format_diagnostics(port_labels, snapshots),
        file=sys.stderr,
        flush=True,
    )

    if all(snapshot["raw_bytes"] == 0 for snapshot in snapshots):
        print(
            "[diagnostic] bytes=0 なので、Pythonはポートを開けていますが、"
            "現時点ではM5Stack側のBluetooth Classic SPP接続がまだ成立していません。",
            file=sys.stderr,
            flush=True,
        )
        print(
            "[diagnostic] M5Stack画面が Connected になっているか、"
            "選択したポートが対象IMUのSPPポートか、同じBT名の古いペアリングが残っていないかを確認してください。",
            file=sys.stderr,
            flush=True,
        )
        tty_hints = [
            f"IMU{index}: {tty_port}"
            for index, tty_port in (
                (index, macos_tty_counterpart(port))
                for index, port in enumerate(port_labels, start=1)
            )
            if tty_port
        ]
        if tty_hints:
            print(
                "[diagnostic] macOSでは同名のttyポートで読める場合があります: "
                + ", ".join(tty_hints),
                file=sys.stderr,
                flush=True,
            )
        return

    for index, snapshot in enumerate(snapshots, start=1):
        if snapshot["invalid_lines"] and snapshot["last_line_preview"]:
            print(
                f"[diagnostic] IMU{index} の最後の無効行候補: "
                f"{snapshot['last_line_preview']!r}",
                file=sys.stderr,
                flush=True,
            )


def monitor_multi_sample_rate(
    ports,
    baudrate,
    interval_seconds,
    timeout_seconds,
    diagnostics_seconds,
    rate_window_seconds,
    source_rate,
    use_tty,
):
    serial, list_ports = import_serial_modules()
    if serial is None:
        return 1

    if interval_seconds <= 0:
        print("集計間隔は0より大きい値を指定してください。")
        return 1

    if diagnostics_seconds <= 0:
        print("診断表示間隔は0より大きい値を指定してください。")
        return 1

    if rate_window_seconds <= 0:
        print("レート計算窓は0より大きい値を指定してください。")
        return 1

    if ports is None:
        imu_count = select_connection_count()
        ports = select_ports_from_list(list_ports, imu_count)
        if ports is None:
            return 1
    else:
        imu_count = len(ports)
        if imu_count == 0:
            print("少なくとも1つのポートを指定してください。")
            return 1

    if use_tty:
        converted_ports = convert_to_macos_tty_ports(ports)
        for original_port, converted_port in zip(ports, converted_ports):
            if original_port != converted_port:
                print(f"Using tty counterpart: {original_port} -> {converted_port}")
        ports = converted_ports

    serial_ports = []
    counters = []
    threads = []
    errors = []
    stop_event = threading.Event()

    try:
        for index, port in enumerate(ports, start=1):
            serial_port = serial.Serial(
                port,
                baudrate=baudrate,
                timeout=timeout_seconds,
            )
            serial_port.reset_input_buffer()
            serial_ports.append(serial_port)
            counters.append(SampleCounter())
            print(f"IMU{index}: Opened serial port {port} ({baudrate} bps)")

        for index, serial_port in enumerate(serial_ports, start=1):
            thread = threading.Thread(
                target=read_serial_lines,
                args=(
                    f"IMU{index}",
                    serial_port,
                    counters[index - 1],
                    stop_event,
                    errors,
                ),
                daemon=True,
            )
            thread.start()
            threads.append(thread)

        if source_rate:
            print(
                f"直近{rate_window_seconds:g}秒のM5側時刻ベースHzを出力します。",
                file=sys.stderr,
            )
        else:
            print("1秒ごとの受信サンプル数を出力します。停止: Ctrl+C")
            if rate_window_seconds > DEFAULT_RATE_WINDOW_SECONDS:
                print(
                    f"直近{rate_window_seconds:g}秒の移動平均Hzを出力します。",
                    file=sys.stderr,
                )
        print_stream_header(len(counters), rate_window_seconds, source_rate)

        last_totals = [0 for _ in counters]
        next_print_time = perf_counter() + interval_seconds
        next_diagnostics_time = perf_counter() + diagnostics_seconds

        while not stop_event.is_set():
            now = perf_counter()
            if now < next_print_time:
                sleep(min(0.01, next_print_time - now))
                continue

            snapshots = [
                counter.snapshot(
                    now=now,
                    rate_window_seconds=rate_window_seconds,
                )
                for counter in counters
            ]
            totals = [snapshot["total_samples"] for snapshot in snapshots]
            if source_rate:
                output_values = [
                    f"{snapshot['source_hz']:.2f}"
                    if snapshot["source_hz"] is not None
                    else "nan"
                    for snapshot in snapshots
                ]
            elif rate_window_seconds <= DEFAULT_RATE_WINDOW_SECONDS:
                output_values = [
                    str(total - last_total)
                    for total, last_total in zip(totals, last_totals)
                ]
            else:
                output_values = [
                    f"{snapshot['window_count'] / rate_window_seconds:.1f}"
                    for snapshot in snapshots
                ]
            print(",".join(output_values), flush=True)
            last_totals = totals
            next_print_time += interval_seconds

            if all(total == 0 for total in totals) and now >= next_diagnostics_time:
                print_no_sample_diagnostics(ports, snapshots)
                next_diagnostics_time = now + diagnostics_seconds
            elif (
                source_rate
                and now >= next_diagnostics_time
                and any(snapshot["source_rows"] == 0 for snapshot in snapshots)
            ):
                print(
                    "[diagnostic] --source-rate には index,timeMs 付きの8列CSVが必要です。"
                    "更新済みArduinoスケッチを書き込んでください。",
                    file=sys.stderr,
                    flush=True,
                )
                next_diagnostics_time = now + diagnostics_seconds

            if errors:
                imu_name, error = errors[0]
                print(f"{imu_name} serial read error: {error}", file=sys.stderr)
                return 1

        if errors:
            imu_name, error = errors[0]
            print(f"{imu_name} serial read error: {error}", file=sys.stderr)
            return 1

    except KeyboardInterrupt:
        print("\nStopping...")
        return 0
    except serial.SerialException as error:
        print(f"Serial connection error: {error}")
        return 1
    finally:
        stop_event.set()
        for thread in threads:
            thread.join(timeout=1.0)
        for serial_port in serial_ports:
            try:
                serial_port.close()
            except serial.SerialException:
                pass

        if counters:
            summaries = []
            for index, counter in enumerate(counters, start=1):
                snapshot = counter.snapshot()
                summaries.append(
                    f"IMU{index}: total={snapshot['total_samples']}, "
                    f"lines={snapshot['received_lines']}, "
                    f"bytes={snapshot['raw_bytes']}, "
                    f"invalid_lines={snapshot['invalid_lines']}, "
                    f"source_rows={snapshot['source_rows']}"
                )
            print("Summary: " + " | ".join(summaries))


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "M5Stack Core2 Bluetooth Classic IMUを複数台接続し、"
            "各IMUの1秒ごとの受信サンプル数をCSV形式で表示します。"
        )
    )
    parser.add_argument(
        "--ports",
        nargs="+",
        help=(
            "使用するシリアルポートをIMU順に指定します。"
            "未指定の場合は接続台数とポートを番号で選択します。"
        ),
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
        help=f"集計間隔（秒）。デフォルト: {DEFAULT_INTERVAL_SECONDS}",
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
        "--rate-window",
        type=float,
        default=DEFAULT_RATE_WINDOW_SECONDS,
        help=(
            "レート計算窓（秒）。1.0なら従来どおり直近1秒のサンプル数、"
            "5や10ならBluetooth受信バーストをならした移動平均Hzを表示します。"
            f"デフォルト: {DEFAULT_RATE_WINDOW_SECONDS}"
        ),
    )
    parser.add_argument(
        "--source-rate",
        action="store_true",
        help=(
            "index,timeMs付き8列CSVから、M5側時刻ベースのHzを表示します。"
            "Bluetooth受信バーストの影響を受けにくい確認用です。"
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
    try:
        args = parse_args()
        return monitor_multi_sample_rate(
            ports=args.ports,
            baudrate=args.baudrate,
            interval_seconds=args.interval,
            timeout_seconds=args.timeout,
            diagnostics_seconds=args.diagnostics,
            rate_window_seconds=args.rate_window,
            source_rate=args.source_rate,
            use_tty=args.use_tty,
        )
    except KeyboardInterrupt:
        print("\nStopping...")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
