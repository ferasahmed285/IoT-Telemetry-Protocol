import subprocess
import time
import os
import sys
import signal

# === Configuration ===
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_PATH = os.path.join(PROJECT_DIR, "server.py")
CLIENT_PATH = os.path.join(PROJECT_DIR, "client.py")

SERVER_LOG = os.path.join(PROJECT_DIR, "server_log.txt")
CLIENT_LOG = os.path.join(PROJECT_DIR, "client_log.txt")
PCAP_FILE = os.path.join(PROJECT_DIR, "baseline_test.pcap")  # placeholder
TEST_DURATION = 65  # seconds (client sends 60s of data)
UDP_PORT = 5005

def run_baseline_test():
    print("=== Starting Baseline Local Test ===\n")

    # Clean up old files
    for f in [SERVER_LOG, CLIENT_LOG, PCAP_FILE]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except PermissionError:
                pass

    # ---- Step 1: Skip tcpdump (Windows-safe) ----
    print("[1] (Skipping tcpdump — not available on Windows)")
    tcpdump = None

    # ---- Step 2: Start Server ----
    print("[2] Starting server...")
    server_out = open(SERVER_LOG, "w", encoding="utf-8")
    server_proc = subprocess.Popen(
        [sys.executable, SERVER_PATH],
        stdout=server_out,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
    )
    time.sleep(2)  # give server time to start

    # ---- Step 3: Start Client ----
    print("[3] Starting client...")
    client_out = open(CLIENT_LOG, "w", encoding="utf-8")
    client_proc = subprocess.Popen(
        [sys.executable, CLIENT_PATH],
        stdout=client_out,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
    )

    # ---- Step 4: Wait for test duration ----
    print(f"[4] Running for {TEST_DURATION} seconds...\n")
    time.sleep(TEST_DURATION)

    # ---- Step 5: Stop processes ----
    print("[5] Stopping client and server...")
    for proc, name in [(client_proc, "Client"), (server_proc, "Server")]:
        try:
            proc.terminate()
            proc.wait(timeout=5)
            print(f"   {name} stopped successfully.")
        except Exception as e:
            print(f"   Warning: could not stop {name}: {e}")

    # ---- Step 6: Stop tcpdump (if used) ----
    if tcpdump:
        print("[6] Stopping packet capture...")
        try:
            if os.name == "nt":
                tcpdump.terminate()
            else:
                tcpdump.send_signal(signal.SIGINT)
            tcpdump.wait(timeout=5)
        except Exception as e:
            print(f"Warning: could not stop tcpdump cleanly: {e}")
    else:
        print("[6] No packet capture process found (skipped).")

    # ---- Step 7: Close logs ----
    server_out.close()
    client_out.close()

    print("\n=== Test Complete ===")
    print("Output files generated:")
    print(f"  • {SERVER_LOG}")
    print(f"  • {CLIENT_LOG}")
    if tcpdump:
        print(f"  • {PCAP_FILE}")
    print("\nCheck 'server_log.txt' for received packets and sequence order.\n")


if __name__ == "__main__":
    run_baseline_test()
