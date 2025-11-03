import socket, struct

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('0.0.0.0', 5005))

print("Server is listening on port 5005...\n")

while True:
    data, addr = sock.recvfrom(1024)

    header = data[:12]
    version, msg_type, device_id, seq_num, timestamp, batching_flag, checksum = struct.unpack('!BBHHIBB', header)

    print(
        f"From {addr} → DeviceID:{device_id}, SeqNum:{seq_num}, Timestamp:{timestamp}, MsgType:{msg_type}, Batch:{batching_flag}")

    if msg_type == 1:
        payload = data[12:]

        try:
            readings = struct.unpack('!fffff', payload)
            readings = [round(val, 2) for val in readings]
            print(f"Readings: {readings}\n")
        except struct.error as e:
            print(f"Error unpacking payload: {e}\n")
    elif msg_type == 0:
        print("Received INIT message.\n")
    else:
        print("Received unknown message type.\n")