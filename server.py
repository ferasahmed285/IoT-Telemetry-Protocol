import socket
import struct
import time
import csv
import argparse
import threading
import signal
import os
import sys
from typing import Dict, Optional

HEADER_FMT = "!BBHHIBB"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
PAYLOAD_FMT = "!fffff"
PAYLOAD_SIZE = struct.calcsize(PAYLOAD_FMT)
CSV_COLUMNS = ["device_id", "seq", "timestamp", "arrival_time", "duplicate_flag", "gap_flag"]

device_state_lock = threading.Lock()
csv_lock = threading.Lock()
shutdown_event = threading.Event()

class DeviceState:
    def __init__(self):
        self.last_seq: Optional[int] = None

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
    arrival_time = time.time()
    if len(data) < HEADER_SIZE:
        print(f"[WARN] Packet from {addr} too short ({len(data)} bytes). Expected at least {HEADER_SIZE}. Ignoring.")
        return
    try:
        version, msg_type, device_id, seq_num, send_ts, batching_flag, checksum = struct.unpack(HEADER_FMT, data[:HEADER_SIZE])
    except struct.error as e:
        print(f"[ERROR] Failed to unpack header from {addr}: {e}")
        return
    expected_checksum = sum(data[:HEADER_SIZE-1]) & 0xFF
    if checksum != expected_checksum:
        print(f"[ERROR] Checksum mismatch from {addr}. Expected {expected_checksum}, got {checksum}. Packet ignored.")
        return
    device_id = int(device_id)
    seq_num = int(seq_num)
    send_ts = int(send_ts)
    duplicate_flag = 0
    gap_flag = 0
    with device_state_lock:
        state = device_states.get(device_id)
        if state is None:
            state = DeviceState()
            device_states[device_id] = state
        last_seq = state.last_seq
        if last_seq is None:
            state.last_seq = seq_num
        else:
            if seq_num <= last_seq:
                duplicate_flag = 1
            else:
                if seq_num > last_seq + 1:
                    gap_flag = 1
                state.last_seq = seq_num
    csv_row = [device_id, seq_num, send_ts, arrival_time, duplicate_flag, gap_flag]
    try:
        append_csv_row(csv_path, csv_row)
    except Exception as e:
        print(f"[ERROR] Failed to write CSV row: {e}")
    send_ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(send_ts))
    arrival_ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(arrival_time))
    print(f"From {addr} → DeviceID:{device_id}, Seq:{seq_num}, SendTS:{send_ts} ({send_ts_str}), Arrive:{arrival_time:.6f} ({arrival_ts_str}), "
          f"MsgType:{msg_type}, Batch:{batching_flag}, Duplicate:{duplicate_flag}, Gap:{gap_flag}")
    if duplicate_flag:
        print("  → Duplicate packet detected: payload processing skipped.\n")
        return
    if msg_type == 2:
        print("  → HEARTBEAT (Alive). Payload not unpacked.\n")
        return
    if msg_type == 0:
        print("  → INIT message.\n")
        return
    if msg_type == 1:
        payload = data[HEADER_SIZE:]
        if len(payload) < PAYLOAD_SIZE:
            print(f"  [WARN] Payload too short ({len(payload)} bytes). Expected {PAYLOAD_SIZE} bytes for msg_type==1. Skipping payload unpack.\n")
            return
        try:
            readings = struct.unpack(PAYLOAD_FMT, payload[:PAYLOAD_SIZE])
            readings = [round(float(x), 2) for x in readings]
            print(f"  → Readings: {readings}\n")
        except struct.error as e:
            print(f"  [ERROR] Failed to unpack payload readings: {e}\n")
            return
    else:
        print("  → Unknown message type: payload not processed.\n")
        return

def server_loop(host: str, port: int, csv_path: str, buffer_size: int = 4096):
    ensure_csv(csv_path)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    sock.settimeout(1.0)
    print(f"Server listening on {host}:{port} -> CSV: {csv_path}\n")
    try:
        while not shutdown_event.is_set():
            try:
                data, addr = sock.recvfrom(buffer_size)
                process_packet(data, addr, csv_path)
            except socket.timeout:
                continue
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"[ERROR] Exception in receive loop: {e}")
    finally:
        sock.close()
        print("Server shutting down...")

def handle_signal(sig, frame):
    print("\nTermination signal received. Shutting down gracefully...")
    shutdown_event.set()

def parse_args():
    p = argparse.ArgumentParser(description="Phase 2 Collector (UDP server) - experiment_results.csv")
    p.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    p.add_argument("--port", type=int, default=5005, help="UDP port to listen on (default: 5005)")
    p.add_argument("--csv", default="experiment_results.csv", help="CSV file path (default: experiment_results.csv)")
    return p.parse_args()

def main():
    args = parse_args()
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    try:
        server_loop(args.host, args.port, args.csv)
    except Exception as e:
        print(f"[FATAL] Server crashed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
