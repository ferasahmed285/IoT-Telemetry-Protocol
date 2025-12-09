import subprocess
import time
import os
import sys
import platform
import shutil
import signal

# === Configuration ===
SERVER_IP = "127.0.0.1"
SERVER_PORT = 5005
INTERFACE = "lo"  # Use 'lo' for Linux loopback. 
TEST_DURATION = 65  # Seconds (covers a 60s test run)

# Scripts
SERVER_SCRIPT = "server.py"
CLIENT_SCRIPT = "client.py"

# OS Detection
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def run_command(cmd):
    if IS_WINDOWS: return
    subprocess.run(cmd, shell=True, check=True)

def cleanup_netem():
    """Removes network rules (Linux only)."""
    if IS_WINDOWS: return
    try:
        subprocess.run(f"tc qdisc del dev {INTERFACE} root", shell=True, 
                       stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    except Exception:
        pass

def set_netem(loss=0, delay=0, jitter=0):
    """Applies network impairment rules using 'tc'."""
    if IS_WINDOWS:
        if loss > 0 or delay > 0:
            log(f"[WARN] Windows detected! Cannot script 'tc'.")
            log(f"       >>> PLEASE MANUALLY CONFIGURE CLUMSY NOW <<<")
            log(f"       Loss: {loss}%, Delay: {delay}ms")
            time.sleep(5)
        return

    cleanup_netem()
    if loss == 0 and delay == 0:
        return

    # Basic netem command structure
    cmd = f"tc qdisc replace dev {INTERFACE} root netem"
    if loss > 0:
        cmd += f" loss {loss}%"
    if delay > 0:
        cmd += f" delay {delay}ms"
        if jitter > 0:
            cmd += f" {jitter}ms"
    
    log(f"[NET] Applying rules: {cmd}")
    run_command(cmd)

def get_capture_cmd(pcap_file):
    """Returns the command to capture packets."""
    # Priority 1: tcpdump (Linux)
    if shutil.which("tcpdump"):
        # -U: Packet-buffered, write immediately
        return ["tcpdump", "-i", INTERFACE, "udp", "port", str(SERVER_PORT), "-w", pcap_file, "-U"]
    
    # Priority 2: tshark (Windows/Linux)
    if shutil.which("tshark"):
        return ["tshark", "-f", f"udp port {SERVER_PORT}", "-w", pcap_file]

    return None

def run_test(scenario_name, interval, loss, delay, jitter):
    """Executes a single test run."""
    log(f"\n{'='*10} SCENARIO: {scenario_name} | Interval: {interval}s {'='*10}")
    
    csv_file = f"results_{scenario_name}_{interval}s.csv"
    pcap_file = f"trace_{scenario_name}_{interval}s.pcap"
    
    # Clean previous run files
    if os.path.exists(csv_file): os.remove(csv_file)
    if os.path.exists(pcap_file): os.remove(pcap_file)

    # 1. Network Setup
    set_netem(loss, delay, jitter)

    # 2. Start PCAP
    cap_cmd = get_capture_cmd(pcap_file)
    cap_proc = None
    if cap_cmd:
        log(f"[PROC] Starting Capture -> {pcap_file}")
        cap_proc = subprocess.Popen(cap_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 3. Start Server
    log("[PROC] Starting Server...")
    # On Windows, using CREATE_NEW_PROCESS_GROUP helps kill the tree later
    cflags = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0
    server_cmd = [sys.executable, SERVER_SCRIPT, "--port", str(SERVER_PORT), "--csv", csv_file]
    server_proc = subprocess.Popen(server_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=cflags)
    time.sleep(2) # Warmup

    # 4. Start Client
    log(f"[PROC] Starting Client (Interval: {interval}s)...")
    client_cmd = [sys.executable, CLIENT_SCRIPT, 
                  "--host", SERVER_IP, 
                  "--port", str(SERVER_PORT), 
                  "--interval", str(interval)]
    client_proc = subprocess.Popen(client_cmd, creationflags=cflags)

    # 5. Wait for test duration
    try:
        # If interval is large (30s), we might need more time to get enough packets? 
        # Requirement says "1s interval, 60s test". 
        # For 30s interval, a 65s test only yields ~2 packets. 
        # Adjust duration if needed, but 65s covers the prompt's requirement for the 1s test.
        wait_time = TEST_DURATION
        if interval >= 5:
            # Extend time for slow intervals to ensure we get data points
            wait_time = max(TEST_DURATION, interval * 5 + 5)
            
        log(f"[WAIT] Running for {wait_time} seconds...")
        client_proc.wait(timeout=wait_time)
    except subprocess.TimeoutExpired:
        log("[TIME] Test finished.")
        if IS_WINDOWS:
            subprocess.run(f"taskkill /F /T /PID {client_proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            client_proc.terminate()

    # 6. Cleanup
    log("[PROC] Stopping Server & Capture...")
    if IS_WINDOWS:
        subprocess.run(f"taskkill /F /T /PID {server_proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if cap_proc:
            subprocess.run(f"taskkill /F /T /PID {cap_proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        server_proc.terminate()
        if cap_proc: cap_proc.terminate()

    cleanup_netem()
    log("[DONE] Run complete.\n")

if __name__ == "__main__":
    if IS_LINUX and os.geteuid() != 0:
        print("Error: Must run as root (sudo) on Linux for 'tc' commands.")
        sys.exit(1)

    try:
        # === 1. Baseline Tests (Varying Intervals) ===
        # Requirement: Test 1s, 5s, 30s reporting intervals 
        for interval in [1, 5, 30]:
            run_test("baseline", interval=interval, loss=0, delay=0, jitter=0)

        # === 2. Loss Tolerance Test ===
        # Requirement: 5% Loss 
        run_test("loss_5pct", interval=1, loss=5, delay=0, jitter=0)

        # === 3. Jitter/Delay Test ===
        # Requirement: 100ms Delay +/- 10ms Jitter 
        run_test("jitter_test", interval=1, loss=0, delay=100, jitter=10)

        print("\nAll experiments finished. Check .csv and .pcap files.")

    except KeyboardInterrupt:
        print("\n[STOP] Interrupted.")
        cleanup_netem()