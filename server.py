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
# CHANGED: Back to 'I' (4-byte int) -> Total 12 Bytes
HEADER_FMT = "!BBHHIBB"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
PAYLOAD_FMT = "!fffff"

CSV_COLUMNS = [
    "device_id", "seq", "timestamp", "arrival_time", 
    "duplicate_flag", "gap_flag", "out_of_order_flag", "cpu_ms_per_report"
]

device_state_lock = threading.Lock()
shutdown_event = threading.Event()

class DeviceState:
    def __init__(self):
        self.highest_seq: int = -1
        self.seen_seqs: Set[int] = set() 

device_states: Dict[int, DeviceState] = {}

def process_packet(data: bytes, addr, csv_writer):
    start_cpu = time.process_time()
    arrival_time = time.time() # Full precision float
    
    if len(data) < HEADER_SIZE:
        return

    try:
        # Unpack Header
        # send_ts is now the 32-bit truncated millis integer
        version, msg_type, device_id, seq_num, send_ts, batching_flag, checksum = struct.unpack(HEADER_FMT, data[:HEADER_SIZE])
    except struct.error:
        return

    device_id = int(device_id)
    seq_num = int(seq_num)

    duplicate_flag = 0
    gap_flag = 0
    out_of_order_flag = 0

    with device_state_lock:
        state = device_states.get(device_id)
        if state is None:
            state = DeviceState()
            device_states[device_id] = state

        if seq_num in state.seen_seqs:
            duplicate_flag = 1
        else:
            state.seen_seqs.add(seq_num)
            if len(state.seen_seqs) > 1000:
                state.seen_seqs.pop()

            if seq_num > state.highest_seq:
                if state.highest_seq != -1 and seq_num > state.highest_seq + 1:
                    gap_flag = 1
                state.highest_seq = seq_num
            else:
                out_of_order_flag = 1

    end_cpu = time.process_time()
    cpu_ms = (end_cpu - start_cpu) * 1000.0

    # Log to CSV
    # Note: 'timestamp' col contains the 32-bit truncated integer from client
    #       'arrival_time' col contains the full server float
    csv_row = [
        device_id, 
        seq_num, 
        send_ts, 
        f"{arrival_time:.6f}", 
        duplicate_flag, 
        gap_flag, 
        out_of_order_flag, 
        f"{cpu_ms:.4f}"
    ]
    
    try:
        csv_writer.writerow(csv_row)
    except Exception as e:
        print(f"[ERROR] CSV write failed: {e}")

    if gap_flag: print(f"GAP DETECTED: Seq {seq_num}")
    if out_of_order_flag: print(f"LATE PACKET: Seq {seq_num}")

def server_loop(host: str, port: int, csv_path: str):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.settimeout(1.0)
    
    print(f"=== Optimized Server Running on {host}:{port} ===")
    
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)
        f.flush()
        
        print(f"=== Logging started: {csv_path} ===\n")

        try:
            while not shutdown_event.is_set():
                try:
                    data, addr = sock.recvfrom(4096)
                    process_packet(data, addr, writer)
                    f.flush()
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