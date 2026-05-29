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

DEVICE_DEFINITIONS = {
    "imu": {
        "label_prefix": "IMU",
        "prompt_name": "IMU",
        "data_columns": 6,
    },
    "posturo": {
        "label_prefix": "Posturo",
        "prompt_name": "重心動揺計",
        "data_columns": 4,
    },
}


class SampleCounter:
    def __init__(self, data_columns=6):
        self.data_columns = data_columns
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
        """data列のみ、または index,timeMs 付きCSVをサンプルとして数える。"""
        values = line.strip().split(",")
        if len(values) not in (self.data_columns, self.data_columns + 2):
            self._add_invalid_line()
            return

        try:
            if len(values) == self.data_columns + 2:
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


def read_nonnegative_int(prompt):
    while True:
        choice = input(prompt).strip()

        try:
            value = int(choice)
        except ValueError:
            print("番号で入力してください。")
            continue

        if value >= 0:
            return value

        print("0以上の数字を入力してください。")


def build_device_configs(imu_count, posturo_count):
    if imu_count < 0 or posturo_count < 0:
        return None

    device_configs = []
    for device_type, count in (("imu", imu_count), ("posturo", posturo_count)):
        definition = DEVICE_DEFINITIONS[device_type]
        for number in range(1, count + 1):
            label = f"{definition['label_prefix']}{number}"
            device_configs.append(
                {
                    "type": device_type,
                    "label": label,
                    "prompt_label": label
                    if device_type == "imu"
                    else f"{definition['prompt_name']}{number}",
                    "data_columns": definition["data_columns"],
                }
            )

    return device_configs


def select_device_configs(imu_count=None, posturo_count=None):
    if imu_count is None and posturo_count is None:
        imu_count = read_nonnegative_int("接続するIMU台数を入力してください: ")
        posturo_count = read_nonnegative_int("接続する重心動揺計台数を入力してください: ")
    else:
        imu_count = 0 if imu_count is None else imu_count
        posturo_count = 0 if posturo_count is None else posturo_count

    device_configs = build_device_configs(imu_count, posturo_count)
    if device_configs is None:
        print("接続台数は0以上の数字を指定してください。")
        return None

    if not device_configs:
        print("IMUまたは重心動揺計を少なくとも1台指定してください。")
        return None

    return device_configs


def infer_device_configs_for_ports(port_count, imu_count=None, posturo_count=None):
    if port_count <= 0:
        print("少なくとも1つのポートを指定してください。")
        return None

    if imu_count is None and posturo_count is None:
        imu_count = port_count
        posturo_count = 0
    elif imu_count is None:
        imu_count = port_count - posturo_count
    elif posturo_count is None:
        posturo_count = port_count - imu_count

    device_configs = build_device_configs(imu_count, posturo_count)
    if device_configs is None:
        print("接続台数は0以上の数字を指定してください。")
        return None

    if len(device_configs) != port_count:
        print(
            "指定したポート数と台数設定が一致しません: "
            f"ports={port_count}, IMU={imu_count}, 重心動揺計={posturo_count}"
        )
        return None

    return device_configs


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


def normalize_device_configs(device_configs_or_count):
    if isinstance(device_configs_or_count, int):
        return build_device_configs(device_configs_or_count, 0)

    return list(device_configs_or_count)


def device_labels(device_configs):
    return [device_config["label"] for device_config in device_configs]


def select_ports_from_list(list_ports, device_configs_or_count):
    device_configs = normalize_device_configs(device_configs_or_count)
    connection_count = len(device_configs)
    ports = sorted(list_ports.comports(), key=lambda port: port.device)

    if not ports:
        print("利用可能なシリアルポートが見つかりません。")
        print("M5Stack Core2 と Bluetooth Classic でペアリング済みか確認してください。")
        return None

    if connection_count > len(ports):
        print(
            f"接続台数 {connection_count} 台に対して、利用可能なポートが {len(ports)} 個しかありません。"
        )
        return None

    print("利用可能なシリアルポート:")
    for index, port_info in enumerate(ports, start=1):
        print(f"  [{index}] {format_port_info(port_info)}")

    selected_ports = []
    selected_numbers = set()

    for device_config in device_configs:
        prompt_label = device_config["prompt_label"]
        while True:
            choice = input(f"{prompt_label}で使用するポート番号を入力してください: ").strip()

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


def print_stream_header(device_configs_or_count, rate_window_seconds, source_rate):
    labels = device_labels(normalize_device_configs(device_configs_or_count))
    if source_rate:
        window_label = f"{rate_window_seconds:g}s"
        columns = [
            f"{label}_source_hz_{window_label}" for label in labels
        ]
    elif rate_window_seconds <= DEFAULT_RATE_WINDOW_SECONDS:
        columns = [f"{label}_samples_per_sec" for label in labels]
    else:
        window_label = f"{rate_window_seconds:g}s"
        columns = [
            f"{label}_rolling_hz_{window_label}" for label in labels
        ]
    print(",".join(columns), flush=True)


def format_diagnostics(port_labels, snapshots, labels=None):
    if labels is None:
        labels = [f"IMU{index}" for index in range(1, len(port_labels) + 1)]

    chunks = []
    for label, port, snapshot in zip(labels, port_labels, snapshots):
        chunks.append(
            f"{label}({port}): "
            f"bytes={snapshot['raw_bytes']}, "
            f"lines={snapshot['received_lines']}, "
            f"valid={snapshot['total_samples']}, "
            f"invalid={snapshot['invalid_lines']}"
        )

    return " | ".join(chunks)


def print_no_sample_diagnostics(port_labels, snapshots, labels=None):
    if labels is None:
        labels = [f"IMU{index}" for index in range(1, len(port_labels) + 1)]

    print(
        "[diagnostic] まだ有効なCSVサンプルを受信できていません: "
        + format_diagnostics(port_labels, snapshots, labels),
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
            f"{label}: {tty_port}"
            for label, tty_port in (
                (label, macos_tty_counterpart(port))
                for label, port in zip(labels, port_labels)
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

    for label, snapshot in zip(labels, snapshots):
        if snapshot["invalid_lines"] and snapshot["last_line_preview"]:
            print(
                f"[diagnostic] {label} の最後の無効行候補: "
                f"{snapshot['last_line_preview']!r}",
                file=sys.stderr,
                flush=True,
            )


def monitor_multi_sample_rate(
    ports,
    imu_count,
    posturo_count,
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
        device_configs = select_device_configs(imu_count, posturo_count)
        if device_configs is None:
            return 1

        ports = select_ports_from_list(list_ports, device_configs)
        if ports is None:
            return 1
    else:
        device_configs = infer_device_configs_for_ports(
            len(ports),
            imu_count=imu_count,
            posturo_count=posturo_count,
        )
        if device_configs is None:
            return 1

    if use_tty:
        converted_ports = convert_to_macos_tty_ports(ports)
        for original_port, converted_port in zip(ports, converted_ports):
            if original_port != converted_port:
                print(f"Using tty counterpart: {original_port} -> {converted_port}")
        ports = converted_ports

    labels = device_labels(device_configs)
    serial_ports = []
    counters = []
    threads = []
    errors = []
    stop_event = threading.Event()

    try:
        for device_config, port in zip(device_configs, ports):
            serial_port = serial.Serial(
                port,
                baudrate=baudrate,
                timeout=timeout_seconds,
            )
            serial_port.reset_input_buffer()
            serial_ports.append(serial_port)
            counters.append(SampleCounter(data_columns=device_config["data_columns"]))
            print(f"{device_config['label']}: Opened serial port {port} ({baudrate} bps)")

        for label, serial_port, counter in zip(labels, serial_ports, counters):
            thread = threading.Thread(
                target=read_serial_lines,
                args=(
                    label,
                    serial_port,
                    counter,
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
        print_stream_header(device_configs, rate_window_seconds, source_rate)

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
                print_no_sample_diagnostics(ports, snapshots, labels)
                next_diagnostics_time = now + diagnostics_seconds
            elif (
                source_rate
                and now >= next_diagnostics_time
                and any(snapshot["source_rows"] == 0 for snapshot in snapshots)
            ):
                print(
                    "[diagnostic] --source-rate には index,timeMs 付きCSVが必要です。"
                    "IMUは8列、重心動揺計は6列の形式にしてください。",
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
            for label, counter in zip(labels, counters):
                snapshot = counter.snapshot()
                summaries.append(
                    f"{label}: total={snapshot['total_samples']}, "
                    f"lines={snapshot['received_lines']}, "
                    f"bytes={snapshot['raw_bytes']}, "
                    f"invalid_lines={snapshot['invalid_lines']}, "
                    f"source_rows={snapshot['source_rows']}"
                )
            print("Summary: " + " | ".join(summaries))


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "M5Stack Core2 Bluetooth Classic IMU/重心動揺計を複数台接続し、"
            "各機器の1秒ごとの受信サンプル数をCSV形式で表示します。"
        )
    )
    parser.add_argument(
        "--ports",
        nargs="+",
        help=(
            "使用するシリアルポートをIMU、重心動揺計の順に指定します。"
            "未指定の場合は接続台数とポートを番号で選択します。"
        ),
    )
    parser.add_argument(
        "--imu-count",
        type=int,
        help=(
            "接続するIMU台数。--ports指定時に重心動揺計と混在させる場合に使います。"
            "未指定かつ--ports指定時は全ポートをIMUとして扱います。"
        ),
    )
    parser.add_argument(
        "--posturo-count",
        type=int,
        help="接続する重心動揺計台数。CSVは index,timeMs,data1,data2,data3,data4 を想定します。",
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
            "index,timeMs付きCSVから、送信元時刻ベースのHzを表示します。"
            "IMUは8列、重心動揺計は6列を想定します。"
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
            imu_count=args.imu_count,
            posturo_count=args.posturo_count,
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
