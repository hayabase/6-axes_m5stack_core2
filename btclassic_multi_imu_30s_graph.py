#!/usr/bin/env python3
"""
M5Stack Core2 Bluetooth Classic 複数IMU 30秒グラフ計測ツール

Bluetooth Classic SPP の仮想シリアルポートを複数開き、接続後3秒待ってから
30秒間の受信サンプル数を計測し、IMUごとの1秒あたり受信サンプル数をグラフ表示します。
"""

import argparse
import math
import sys
import threading
from time import perf_counter, sleep

from btclassic_multi_imu_sample_rate_monitor import (
    DEFAULT_BAUDRATE,
    DEFAULT_DIAGNOSTICS_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    convert_to_macos_tty_ports,
    import_serial_modules,
    print_no_sample_diagnostics,
    read_serial_lines,
    select_connection_count,
    select_ports_from_list,
)


DEFAULT_WARMUP_SECONDS = 3.0
DEFAULT_DURATION_SECONDS = 30.0
DEFAULT_BIN_SECONDS = 1.0


class GraphSampleCollector:
    def __init__(self):
        self._lock = threading.Lock()
        self.reset_measurement()

    def reset_measurement(self):
        with self._lock:
            self.total_samples = 0
            self.invalid_lines = 0
            self.received_lines = 0
            self.raw_bytes = 0
            self.last_line_preview = ""
            self.host_sample_times = []
            self.source_samples = []

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

        now = perf_counter()
        with self._lock:
            self.total_samples += 1
            self.host_sample_times.append(now)
            if sample_index is not None and sample_time_ms is not None:
                self.source_samples.append((sample_index, sample_time_ms, now))

    def _add_invalid_line(self):
        with self._lock:
            self.invalid_lines += 1

    def snapshot(self):
        with self._lock:
            return {
                "total_samples": self.total_samples,
                "invalid_lines": self.invalid_lines,
                "received_lines": self.received_lines,
                "raw_bytes": self.raw_bytes,
                "last_line_preview": self.last_line_preview,
                "source_rows": len(self.source_samples),
                "host_sample_times": list(self.host_sample_times),
                "source_samples": list(self.source_samples),
            }


def import_matplotlib():
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        print("Missing Python dependency: matplotlib")
        print("Install it with: pip install matplotlib")
        return None

    return plt


def make_receive_rate_series(host_sample_times, start_time, duration_seconds, bin_seconds):
    bin_count = max(1, int(math.ceil(duration_seconds / bin_seconds)))
    counts = [0 for _ in range(bin_count)]

    for sample_time in host_sample_times:
        elapsed = sample_time - start_time
        if not 0 <= elapsed < duration_seconds:
            continue

        bin_index = int(elapsed // bin_seconds)
        if 0 <= bin_index < bin_count:
            counts[bin_index] += 1

    x_values = [(index + 0.5) * bin_seconds for index in range(bin_count)]
    hz_values = [count / bin_seconds for count in counts]
    return x_values, hz_values


def source_average_hz(source_samples):
    if len(source_samples) < 2:
        return None

    first_index, first_time_ms, _ = source_samples[0]
    last_index, last_time_ms, _ = source_samples[-1]
    elapsed_seconds = (last_time_ms - first_time_ms) / 1000.0
    if elapsed_seconds <= 0:
        return None

    return (last_index - first_index) / elapsed_seconds


def plot_results(
    snapshots,
    start_time,
    warmup_seconds,
    duration_seconds,
    bin_seconds,
    save_path,
):
    plt = import_matplotlib()
    if plt is None:
        return 1

    fig, ax = plt.subplots(figsize=(10, 5.5))
    for index, snapshot in enumerate(snapshots, start=1):
        x_values, hz_values = make_receive_rate_series(
            snapshot["host_sample_times"],
            start_time,
            duration_seconds,
            bin_seconds,
        )
        source_hz = source_average_hz(snapshot["source_samples"])
        label = f"IMU{index}"
        if source_hz is not None:
            label += f" (source avg {source_hz:.1f} Hz)"

        ax.plot(x_values, hz_values, marker="o", linewidth=1.8, label=label)

    ax.set_title(f"Bluetooth Classic IMU receive rate after {warmup_seconds:g}s warmup")
    ax.set_xlabel("Measurement time (s)")
    ax.set_ylabel(f"Received samples per {bin_seconds:g}s (Hz)")
    ax.set_xlim(0, duration_seconds)
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150)
        print(f"Saved graph: {save_path}")

    print("グラフを閉じるとプログラムが終了します。")
    plt.show()
    return 0


def validate_positive(name, value):
    if value <= 0:
        print(f"{name}は0より大きい値を指定してください。")
        return False

    return True


def wait_with_diagnostics(
    label,
    seconds,
    counters,
    ports,
    diagnostics_seconds,
    stop_event,
    errors,
):
    print(f"{label}: {seconds:g}秒")
    end_time = perf_counter() + seconds
    next_progress_second = 0
    next_diagnostics_time = perf_counter() + diagnostics_seconds

    while not stop_event.is_set():
        now = perf_counter()
        remaining = end_time - now
        if remaining <= 0:
            break

        elapsed = seconds - remaining
        current_progress_second = int(elapsed)
        if current_progress_second > next_progress_second:
            next_progress_second = current_progress_second
            print(f"  {label}: {elapsed:.0f}/{seconds:g}s", flush=True)

        if errors:
            imu_name, error = errors[0]
            print(f"{imu_name} serial read error: {error}", file=sys.stderr)
            return 1

        if now >= next_diagnostics_time:
            snapshots = [counter.snapshot() for counter in counters]
            if all(snapshot["total_samples"] == 0 for snapshot in snapshots):
                print_no_sample_diagnostics(ports, snapshots)
            next_diagnostics_time = now + diagnostics_seconds

        sleep(min(0.02, remaining))

    return 0


def monitor_and_plot(
    ports,
    baudrate,
    timeout_seconds,
    diagnostics_seconds,
    warmup_seconds,
    duration_seconds,
    bin_seconds,
    use_tty,
    save_path,
):
    serial, list_ports = import_serial_modules()
    if serial is None:
        return 1
    if import_matplotlib() is None:
        return 1

    validations = [
        validate_positive("読み取りタイムアウト", timeout_seconds),
        validate_positive("診断表示間隔", diagnostics_seconds),
        validate_positive("接続後待機時間", warmup_seconds),
        validate_positive("計測時間", duration_seconds),
        validate_positive("グラフ集計幅", bin_seconds),
    ]
    if not all(validations):
        return 1

    if bin_seconds > duration_seconds:
        print("グラフ集計幅は計測時間以下にしてください。")
        return 1

    if ports is None:
        imu_count = select_connection_count()
        ports = select_ports_from_list(list_ports, imu_count)
        if ports is None:
            return 1
    elif len(ports) == 0:
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
    measurement_start = None
    snapshots = []

    try:
        for index, port in enumerate(ports, start=1):
            serial_port = serial.Serial(
                port,
                baudrate=baudrate,
                timeout=timeout_seconds,
            )
            serial_port.reset_input_buffer()
            serial_ports.append(serial_port)
            counters.append(GraphSampleCollector())
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

        warmup_result = wait_with_diagnostics(
            "接続後待機",
            warmup_seconds,
            counters,
            ports,
            diagnostics_seconds,
            stop_event,
            errors,
        )
        if warmup_result:
            return warmup_result

        for counter in counters:
            counter.reset_measurement()

        measurement_start = perf_counter()
        measurement_result = wait_with_diagnostics(
            "計測",
            duration_seconds,
            counters,
            ports,
            diagnostics_seconds,
            stop_event,
            errors,
        )
        if measurement_result:
            return measurement_result

        snapshots = [counter.snapshot() for counter in counters]
        if all(snapshot["total_samples"] == 0 for snapshot in snapshots):
            print_no_sample_diagnostics(ports, snapshots)

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

    if measurement_start is None:
        return 1

    return plot_results(
        snapshots,
        measurement_start,
        warmup_seconds,
        duration_seconds,
        bin_seconds,
        save_path,
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "M5Stack Core2 Bluetooth Classic IMUを複数台接続し、"
            "接続後3秒待ってから30秒間の受信サンプル数をグラフ表示します。"
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
        "--warmup",
        type=float,
        default=DEFAULT_WARMUP_SECONDS,
        help=f"接続後、計測開始前に待つ秒数。デフォルト: {DEFAULT_WARMUP_SECONDS}",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_DURATION_SECONDS,
        help=f"計測する秒数。デフォルト: {DEFAULT_DURATION_SECONDS}",
    )
    parser.add_argument(
        "--bin",
        type=float,
        default=DEFAULT_BIN_SECONDS,
        help=f"グラフの集計幅（秒）。デフォルト: {DEFAULT_BIN_SECONDS}",
    )
    parser.add_argument(
        "--save",
        help="グラフをPNGなどで保存するパス。未指定なら表示のみ行います。",
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
    return monitor_and_plot(
        ports=args.ports,
        baudrate=args.baudrate,
        timeout_seconds=args.timeout,
        diagnostics_seconds=args.diagnostics,
        warmup_seconds=args.warmup,
        duration_seconds=args.duration,
        bin_seconds=args.bin,
        use_tty=args.use_tty,
        save_path=args.save,
    )


if __name__ == "__main__":
    raise SystemExit(main())
