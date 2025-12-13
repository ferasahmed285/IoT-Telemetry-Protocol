import socket
import struct
import time
import argparse
import random
import sys

HEADER_FMT = "!BBHHIBB"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

MSG_INIT = 0
MSG_DATA = 1
MSG_HEARTBEAT = 2

def build_packet(version, msg_type, device_id, seq_num, send_ts_float, batching_flag=0, payload=b''):
    ts_masked = int(send_ts_float * 1000) & 0xFFFFFFFF

    temp_header = struct.pack(
        HEADER_FMT,
        version,
        msg_type,
        device_id,
        seq_num,
        ts_masked,
        batching_flag,
        0
    )

    checksum = sum(temp_header) & 0xFF

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

def build_payload(batch_size):
    readings = [round(random.uniform(20.0, 30.0), 2) for _ in range(batch_size)]
    fmt = "!" + "f" * batch_size
    return struct.pack(fmt, *readings), readings

def log(msg):
    print(f"[Client] {msg}")

def client_loop(host, port, device_id, interval, batch_size):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    addr = (host, port)

    seq_num = 0
    version = 1

    log(f"Started → Target: {host}:{port} | Interval: {interval}s | BatchSize: {batch_size}")

    packet = build_packet(version, MSG_INIT, device_id, seq_num, time.time())
    sock.sendto(packet, addr)
    log(f"Sent INIT → Dev:{device_id}, Seq:{seq_num}")
    seq_num += 1

    try:
        while True:
            jitter = random.uniform(-0.1, 0.1) * interval
            time.sleep(max(0, interval + jitter))

            send_ts = time.time()

            if random.random() < 0.2:
                packet = build_packet(version, MSG_HEARTBEAT, device_id, seq_num, send_ts)
                log_msg = f"Sent HEARTBEAT → Dev:{device_id}, Seq:{seq_num}"
            else:
                payload_bytes, readings = build_payload(batch_size)
                packet = build_packet(
                    version,
                    MSG_DATA,
                    device_id,
                    seq_num,
                    send_ts,
                    batching_flag=batch_size,
                    payload=payload_bytes
                )
                log_msg = f"Sent DATA (Batch {batch_size}) → Seq:{seq_num}, Readings:{readings}"

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
    p = argparse.ArgumentParser(description="IoT Sensor Client")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5005)
    p.add_argument("--device", type=int, default=1001)
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--batch", type=int, default=5)
    return p.parse_args()

def main():
    args = parse_args()
    client_loop(args.host, args.port, args.device, args.interval, args.batch)

if __name__ == "__main__":
    main()
