import subprocess
import time
import os
import sys
import signal
import platform
import shutil

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_PATH = os.path.join(PROJECT_DIR, "server.py")
CLIENT_PATH = os.path.join(PROJECT_DIR, "client.py")

SERVER_LOG = os.path.join(PROJECT_DIR, "server_log.txt")
CLIENT_LOG = os.path.join(PROJECT_DIR, "client_log.txt")
PCAP_FILE = os.path.join(PROJECT_DIR, "baseline_test.pcap")
TEST_DURATION = 65
UDP_PORT = 5005

def get_platform_flags():
    flags = 0
    if platform.system() == "Windows":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP
    return flags

def run_baseline_test():
    print(f"=== Starting Baseline Test on {platform.system()} ===\n")

    for f in [SERVER_LOG, CLIENT_LOG, PCAP_FILE]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except PermissionError:
                print(f"[WARN] Could not delete {f}")

    tcpdump_proc = None
    tcpdump_path = shutil.which("tcpdump")

    if platform.system() == "Linux" and tcpdump_path:
        print("[1] Starting tcpdump...")
        try:
            cmd = [
                "sudo", tcpdump_path,
                "-i", "lo",
                "-U",
                "-w", PCAP_FILE,
                "udp", "port", str(UDP_PORT)
            ]
            tcpdump_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(2)
        except Exception as e:
            print(f"[WARN] Failed to start tcpdump: {e}")
    else:
        print("[1] Skipping packet capture")

    p_flags = get_platform_flags()

    print("[2] Starting server...")
    server_out = open(SERVER_LOG, "w", encoding="utf-8")
    server_proc = subprocess.Popen(
        [sys.executable, "-u", SERVER_PATH],
        stdout=server_out,
        stderr=subprocess.STDOUT,
        creationflags=p_flags
    )
    time.sleep(2)

    print("[3] Starting client...")
    client_out = open(CLIENT_LOG, "w", encoding="utf-8")
    client_proc = subprocess.Popen(
        [sys.executable, "-u", CLIENT_PATH],
        stdout=client_out,
        stderr=subprocess.STDOUT,
        creationflags=p_flags
    )

    print(f"[4] Running for {TEST_DURATION} seconds...\n")
    try:
        time.sleep(TEST_DURATION)
    except KeyboardInterrupt:
        print("\n[!] Interrupted by user.")

    print("[5] Stopping client and server...")

    def stop_process(proc, name):
        if not proc:
            return
        try:
            if platform.system() == "Windows":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            else:
                proc.terminate()
            proc.wait(timeout=5)
            print(f"   {name} stopped successfully.")
        except Exception as e:
            print(f"   Warning: could not stop {name}: {e}")

    stop_process(client_proc, "Client")
    stop_process(server_proc, "Server")

    if tcpdump_proc:
        print("[6] Stopping packet capture...")
        try:
            if platform.system() == "Windows":
                tcpdump_proc.terminate()
            else:
                tcpdump_proc.send_signal(signal.SIGINT)
            tcpdump_proc.wait(timeout=5)
            if os.path.exists(PCAP_FILE):
                os.system(f"sudo chown $USER:$USER {PCAP_FILE}")
        except Exception as e:
            print(f"Warning: could not stop tcpdump cleanly: {e}")

    server_out.close()
    client_out.close()

    print("\n=== Test Complete ===")
    print("Output files generated:")
    print(f"  • {SERVER_LOG}")
    print(f"  • {CLIENT_LOG}")
    if tcpdump_proc:
        print(f"  • {PCAP_FILE}")
    print()

if __name__ == "__main__":
    run_baseline_test()