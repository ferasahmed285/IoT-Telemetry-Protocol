import socket
import struct
import time
import argparse
import random

HEADER_FMT = "!BBHHIBB"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

PAYLOAD_FMT = "!fffff"
PAYLOAD_SIZE = struct.calcsize(PAYLOAD_FMT)

MSG_INIT = 0
MSG_DATA = 1
MSG_HEARTBEAT = 2

def build_header(version, msg_type, device_id, seq_num, send_ts, batching_flag=0, checksum=0):
    return struct.pack(
        HEADER_FMT,
        version,
        msg_type,
        device_id,
        seq_num,
        int(send_ts),
        batching_flag,
        checksum
    )

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

    init_header = build_header(version, MSG_INIT, device_id, seq_num, time.time())
    sock.sendto(init_header, addr)
    log("Sent INIT")

    while True:
        jitter = random.uniform(-0.1, 0.1) * interval
        time.sleep(interval + jitter)
        send_ts = time.time()

        try:
            if random.random() < 0.2:
                header = build_header(version, MSG_HEARTBEAT, device_id, seq_num, send_ts)
                sock.sendto(header, addr)
                log(f"Sent HEARTBEAT → Dev:{device_id}, Seq:{seq_num}")
            else:
                header = build_header(version, MSG_DATA, device_id, seq_num, send_ts)
                payload, readings = build_payload()
                packet = header + payload
                sock.sendto(packet, addr)
                log(f"Sent DATA → Dev:{device_id}, Seq:{seq_num}, Readings:{readings}, Timestamp:{int(send_ts)}")
                seq_num += 1
        except Exception as e:
            log(f"Socket error → retrying | Error: {e}")
            try:
                sock.sendto(packet, addr)
            except:
                log("Retry failed — continuing")

def parse_args():
    p = argparse.ArgumentParser(description="Enhanced Phase 2 Sensor Client")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5005)
    p.add_argument("--device", type=int, default=1)
    p.add_argument("--interval", type=float, default=1.0)
    return p.parse_args()

def main():
    args = parse_args()
    client_loop(args.host, args.port, args.device, args.interval)

if __name__ == "__main__":
    main()
