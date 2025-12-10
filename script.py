import subprocess
import time
import os
import sys
import signal
import platform
import shutil

# === Configuration ===
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_PATH = os.path.join(PROJECT_DIR, "server.py")
CLIENT_PATH = os.path.join(PROJECT_DIR, "client.py")

SERVER_LOG = os.path.join(PROJECT_DIR, "server_log.txt")
CLIENT_LOG = os.path.join(PROJECT_DIR, "client_log.txt")
PCAP_FILE = os.path.join(PROJECT_DIR, "baseline_test.pcap")
TEST_DURATION = 65  # seconds
UDP_PORT = 5005

def get_platform_flags():
    """Returns OS-specific process creation flags."""
    flags = 0
    if platform.system() == "Windows":
        # Windows-specific flag to allow independent termination
        flags = subprocess.CREATE_NEW_PROCESS_GROUP
    return flags

def run_baseline_test():
    print(f"=== Starting Baseline Test on {platform.system()} ===\n")

    # Clean up old files
    for f in [SERVER_LOG, CLIENT_LOG, PCAP_FILE]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except PermissionError:
                print(f"[WARN] Could not delete {f} (file in use?)")

    # ---- Step 1: Packet Capture (OS Dependent) ----
    tcpdump_proc = None
    tcpdump_path = shutil.which("tcpdump")

    # Only run tcpdump if we are on Linux/WSL and the tool exists
    if platform.system() == "Linux" and tcpdump_path:
        print("[1] Starting tcpdump (sudo required)...")
        try:
            # -i lo: Loopback interface (localhost)
            # -U: Packet-buffered (writes to file immediately)
            # -w: Write to file
            cmd = ["sudo", tcpdump_path, "-i", "lo", "-U", "-w", PCAP_FILE, "udp", "port", str(UDP_PORT)]
            
            # Start tcpdump (Standard output suppressed)
            tcpdump_proc = subprocess.Popen(
                cmd, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
            time.sleep(2) # Wait for sudo prompt or initialization
        except Exception as e:
            print(f"[WARN] Failed to start tcpdump: {e}")
    else:
        print("[1] Skipping packet capture (Not Linux or tcpdump not found)")

    # Define flags based on OS
    p_flags = get_platform_flags()

    # ---- Step 2: Start Server ----
    print("[2] Starting server...")
    server_out = open(SERVER_LOG, "w", encoding="utf-8")
    server_proc = subprocess.Popen(
        [sys.executable, "-u", SERVER_PATH],  # <--- ADD "-u" HERE
        stdout=server_out,
        stderr=subprocess.STDOUT,
        creationflags=p_flags 
    )
    time.sleep(2)

    # ---- Step 3: Start Client ----
    print("[3] Starting client...")
    client_out = open(CLIENT_LOG, "w", encoding="utf-8")
    client_proc = subprocess.Popen(
        [sys.executable, "-u", CLIENT_PATH],  # <--- ADD "-u" HERE
        stdout=client_out,
        stderr=subprocess.STDOUT,
        creationflags=p_flags
    )

    # ---- Step 4: Wait for test duration ----
    print(f"[4] Running for {TEST_DURATION} seconds...\n")
    try:
        time.sleep(TEST_DURATION)
    except KeyboardInterrupt:
        print("\n[!] Interrupted by user.")

    # ---- Step 5: Stop processes ----
    print("[5] Stopping client and server...")
    
    # Helper to kill processes safely on both OSs
    def stop_process(proc, name):
        if not proc: return
        try:
            if platform.system() == "Windows":
                # Force kill tree on Windows
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], 
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                # Terminate on Linux
                proc.terminate()
            
            proc.wait(timeout=5)
            print(f"   {name} stopped successfully.")
        except Exception as e:
            print(f"   Warning: could not stop {name}: {e}")

    stop_process(client_proc, "Client")
    stop_process(server_proc, "Server")

    # ---- Step 6: Stop tcpdump ----
    if tcpdump_proc:
        print("[6] Stopping packet capture...")
        try:
            # TCPDump needs SIGINT (Ctrl+C) to flush the buffer cleanly
            if platform.system() == "Windows":
                tcpdump_proc.terminate()
            else:
                tcpdump_proc.send_signal(signal.SIGINT)
            
            tcpdump_proc.wait(timeout=5)
            # Fix file permissions if created by sudo
            if os.path.exists(PCAP_FILE):
                os.system(f"sudo chown $USER:$USER {PCAP_FILE}")
                
        except Exception as e:
            print(f"Warning: could not stop tcpdump cleanly: {e}")

    # ---- Step 7: Close logs ----
    server_out.close()
    client_out.close()

    print("\n=== Test Complete ===")
    print("Output files generated:")
    print(f"  • {SERVER_LOG}")
    print(f"  • {CLIENT_LOG}")
    if tcpdump_proc:
        print(f"  • {PCAP_FILE}")
    print("\nCheck 'server_log.txt' for received packets and sequence order.\n")

if __name__ == "__main__":
    run_baseline_test()