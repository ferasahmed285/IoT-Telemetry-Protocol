import socket, struct, time

server_ip = '127.0.0.1'
server_port = 5005
device_id = 1001
seq_num = 0

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

msg_type = 0
timestamp = int(time.time())
batching_flag = 0
checksum = 0

header = struct.pack('!BBHHIBB', 1, msg_type, device_id, seq_num, timestamp, batching_flag, checksum)
sock.sendto(header, (server_ip, server_port))

msg_type = 1
for i in range(60):
    time.sleep(1)
    seq_num += 1
    timestamp = int(time.time())

    header = struct.pack('!BBHHIBB', 1, msg_type, device_id, seq_num, timestamp, batching_flag, checksum)

    payload = struct.pack('!fffff', 23.5, 45.2, 3.3, 1.1, 0.0)

    packet = header + payload
    sock.sendto(packet, (server_ip, server_port))

print("Client finished sending.")