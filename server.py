import socket
import struct
import time
import csv
import argparse
import threading
import signal
import os
import sys
from typing import Dict, Optional, Set

# === Protocol Constants ===
HEADER_FMT = "!BBHHIBB"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
PAYLOAD_FMT = "!fffff"
PAYLOAD_SIZE = struct.calcsize(PAYLOAD_FMT)

# === Updated CSV Columns (added cpu_ms_per_report) ===
CSV_COLUMNS = [
    "device_id", "seq", "timestamp", "arrival_time", 
    "duplicate_flag", "gap_flag", "out_of_order_flag", "cpu_ms_per_report"
]

device_state_lock = threading.Lock()
csv_lock = threading.Lock()
shutdown_event = threading.Event()

class DeviceState:
    def __init__(self):
        self.highest_seq: int = -1
        # Keep track of recent seq numbers to distinguish duplicates from late packets
        self.seen_seqs: Set[int] = set() 

device_states: Dict[int, DeviceState] = {}

def ensure_csv(csv_path: str):
    if not os.path.exists(csv_path):
        with csv_lock:
            with open(csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(CSV_COLUMNS)

def append_csv_row(csv_path: str, row: list):
    with csv_lock:
        with open(csv_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(row)

def process_packet(data: bytes, addr, csv_path: str):
    # [Metric] Start CPU timer
    start_cpu = time.process_time()
    
    arrival_time = time.time()
    
    if len(data) < HEADER_SIZE:
        print(f"[WARN] Packet too short ({len(data)} bytes). Ignoring.")
        return

    try:
        # Unpack Header
        version, msg_type, device_id, seq_num, send_ts, batching_flag, checksum = struct.unpack(HEADER_FMT, data[:HEADER_SIZE])
    except struct.error as e:
        print(f"[ERROR] Header unpack failed: {e}")
        return

    # Verify Checksum
    expected_checksum = sum(data[:HEADER_SIZE-1]) & 0xFF
    if checksum != expected_checksum:
        print(f"[ERROR] Checksum mismatch! Expected {expected_checksum}, got {checksum}. Dropping.")
        return

    # Normalize types
    device_id = int(device_id)
    seq_num = int(seq_num)
    send_ts = int(send_ts)

    # State Tracking Flags
    duplicate_flag = 0
    gap_flag = 0
    out_of_order_flag = 0  # New flag for Jitter analysis

    with device_state_lock:
        state = device_states.get(device_id)
        if state is None:
            state = DeviceState()
            device_states[device_id] = state

        # Logic: Distinguish Duplicate vs. Out-of-Order
        if seq_num in state.seen_seqs:
            duplicate_flag = 1
        else:
            # It's a new packet (not seen before)
            state.seen_seqs.add(seq_num)
            
            # Manage memory: Keep set size reasonable (optional simple pruning)
            if len(state.seen_seqs) > 1000:
                state.seen_seqs.pop()

            if seq_num > state.highest_seq:
                # Normal case or Gap
                if state.highest_seq != -1 and seq_num > state.highest_seq + 1:
                    gap_flag = 1
                state.highest_seq = seq_num
            else:
                # New packet, but sequence is lower than highest -> Late arrival (Jitter)
                out_of_order_flag = 1

    # [Metric] Stop CPU timer and convert to ms
    end_cpu = time.process_time()
    cpu_ms = (end_cpu - start_cpu) * 1000.0

    # Log to CSV
    csv_row = [device_id, seq_num, send_ts, arrival_time, duplicate_flag, gap_flag, out_of_order_flag, f"{cpu_ms:.4f}"]
    try:
        append_csv_row(csv_path, csv_row)
    except Exception as e:
        print(f"[ERROR] CSV write failed: {e}")

    # Console Output
    status = []
    if duplicate_flag: status.append("DUPLICATE")
    if gap_flag: status.append("GAP DETECTED")
    if out_of_order_flag: status.append("LATE/REORDERED")
    
    status_str = f"[{'|'.join(status)}]" if status else "[OK]"
    
    print(f"Device:{device_id} Seq:{seq_num:<5} TS:{send_ts} {status_str}")

    # Payload Processing (Only if not duplicate and is DATA)
    if not duplicate_flag and msg_type == 1: # MSG_DATA
        payload = data[HEADER_SIZE:]
        if len(payload) >= PAYLOAD_SIZE:
            try:
                readings = struct.unpack(PAYLOAD_FMT, payload[:PAYLOAD_SIZE])
                print(f"   >>> Readings: {[round(r, 2) for r in readings]}")
            except struct.error:
                print("   >>> [Error unpacking payload]")

def server_loop(host: str, port: int, csv_path: str):
    ensure_csv(csv_path)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.settimeout(1.0)
    
    print(f"=== Collector Server Running on {host}:{port} ===")
    print(f"=== Logging to: {csv_path} ===\n")

    try:
        while not shutdown_event.is_set():
            try:
                data, addr = sock.recvfrom(4096)
                process_packet(data, addr, csv_path)
            except socket.timeout:
                continue
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"[ERROR] {e}")
    finally:
        sock.close()
        print("\nServer stopped.")

def handle_signal(sig, frame):
    shutdown_event.set()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--csv", default="experiment_results.csv")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    server_loop(args.host, args.port, args.csv)

if __name__ == "__main__":
    main()