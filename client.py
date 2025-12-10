import socket
import struct
import time
import argparse
import random
import sys

# === CHANGED: Back to 12 Bytes (Standard IoT Requirement) ===
# Format: Version(1), MsgType(1), DeviceID(2), SeqNum(2), TS(4), Batch(1), Checksum(1)
HEADER_FMT = "!BBHHIBB"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
PAYLOAD_FMT = "!fffff"

MSG_INIT = 0
MSG_DATA = 1
MSG_HEARTBEAT = 2

def build_packet(version, msg_type, device_id, seq_num, send_ts_float, batching_flag=0, payload=b''):
    # === CRITICAL CHANGE: Truncate Timestamp to 32-bit Milliseconds ===
    # We take current time * 1000, convert to int, and mask to 32 bits.
    # This fits in 4 bytes ('I') while keeping ms precision.
    ts_masked = int(send_ts_float * 1000) & 0xFFFFFFFF

    # 1. Build header with Checksum = 0
    temp_header = struct.pack(
        HEADER_FMT,
        version,
        msg_type,
        device_id,
        seq_num,
        ts_masked, 
        batching_flag,
        0  # Placeholder
    )
    
    # 2. Calculate Checksum
    checksum = sum(temp_header) & 0xFF
    
    # 3. Re-pack
    final_header = struct.pack(
        HEADER_FMT,
        version,
        msg_type,
        device_id,
        seq_num,
        ts_masked,
        batching_flag,
        checksum
    )
    
    return final_header + payload

def build_payload():
    readings = [round(random.uniform(20.0, 30.0), 2) for _ in range(5)]
    return struct.pack(PAYLOAD_FMT, *readings), readings

def log(msg):
    print(f"[Client] {msg}")

def client_loop(host, port, device_id, interval):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    addr = (host, port)
    
    seq_num = 0
    version = 1
    
    log(f"Started → Sending to {host}:{port} every {interval}s")

    # --- Send INIT ---
    packet = build_packet(version, MSG_INIT, device_id, seq_num, time.time())
    sock.sendto(packet, addr)
    log(f"Sent INIT → Dev:{device_id}, Seq:{seq_num}")
    seq_num += 1 

    try:
        while True:
            # Jitter: +/- 10%
            jitter = random.uniform(-0.1, 0.1) * interval
            time.sleep(max(0, interval + jitter))
            
            send_ts = time.time()
            
            # 20% Chance of Heartbeat
            if random.random() < 0.2:
                packet = build_packet(version, MSG_HEARTBEAT, device_id, seq_num, send_ts)
                log_msg = f"Sent HEARTBEAT → Dev:{device_id}, Seq:{seq_num}"
            else:
                payload_bytes, readings = build_payload()
                packet = build_packet(version, MSG_DATA, device_id, seq_num, send_ts, payload=payload_bytes)
                log_msg = f"Sent DATA → Dev:{device_id}, Seq:{seq_num}, Readings:{readings}"

            try:
                sock.sendto(packet, addr)
                log(log_msg)
                seq_num += 1
            except Exception as e:
                log(f"Socket send error: {e}")

    except KeyboardInterrupt:
        log("Stopping client manually.")
    finally:
        sock.close()

def parse_args():
    p = argparse.ArgumentParser(description="Phase 2 Sensor Client")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5005)
    p.add_argument("--device", type=int, default=1001)
    p.add_argument("--interval", type=float, default=1.0, help="Reporting interval in seconds")
    return p.parse_args()

def main():
    args = parse_args()
    client_loop(args.host, args.port, args.device, args.interval)

if __name__ == "__main__":
    main()