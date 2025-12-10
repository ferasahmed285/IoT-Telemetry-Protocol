import subprocess
import time
import os
import sys
import platform
import shutil
import csv

# === Configuration ===
SERVER_IP = "127.0.0.1"
SERVER_PORT = 5005
TEST_DURATION = 70 

SERVER_SCRIPT = "server.py"
CLIENT_SCRIPT = "client.py"

# Detect OS
IS_WINDOWS = platform.system() == "Windows"
# Linux uses 'lo' (loopback), Windows requires manual selection or defaults to ID 1
INTERFACE = "lo" if not IS_WINDOWS else None 

# === Protocol Constants ===
PACKET_SIZE_BYTES = 12 + 20 

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def check_requirements():
    """Checks for root on Linux."""
    if not IS_WINDOWS and os.geteuid() != 0:
        log("[ERR] On Linux/WSL, this script must be run as root (sudo) to use 'netem'.")
        sys.exit(1)

def get_tshark_path():
    """Finds TShark executable on both OSes."""
    # Check PATH first
    tshark = shutil.which("tshark")
    if tshark: return tshark
    
    # Check standard Windows paths
    if IS_WINDOWS:
        paths = [
            r"C:\Program Files\Wireshark\tshark.exe", 
            r"C:\Program Files (x86)\Wireshark\tshark.exe"
        ]
        for p in paths:
            if os.path.exists(p): return p
    return None

def select_interface_windows(tshark_bin):
    """Helps pick the loopback adapter on Windows."""
    if not tshark_bin: return "1"
    
    print("\n" + "="*60)
    print("WINDOWS NETWORK INTERFACE SELECTION")
    print("="*60)
    try:
        # List interfaces
        subprocess.run([tshark_bin, "-D"])
    except Exception as e:
        print(f"Error listing interfaces: {e}")
        return "1"

    print("-" * 60)
    print("Look for 'Adapter for loopback traffic capture' or similar.")
    choice = input("Enter Interface Number (e.g., 4): ").strip()
    return choice

def set_netem(loss=0, delay=0, jitter=0):
    """Applies network impairments based on OS."""
    
    if IS_WINDOWS:
        # Windows: Prompt user for Clumsy
        if loss > 0 or delay > 0:
            log(f"\n[WARN] Windows Detected. Automation paused for setup.")
            log(f"       >>> ACTION REQUIRED: ENABLE CLUMSY NOW <<<")
            log(f"       1. Open Clumsy")
            log(f"       2. Filter: udp and udp.DstPort == {SERVER_PORT}")
            
            if loss > 0:
                log(f"       3. Check 'Drop' -> Set to {loss}.0 %")
            if delay > 0:
                log(f"       3. Check 'Lag' -> Set to {delay} ms")
                if jitter > 0:
                     log(f"          (Note: If Clumsy has no Jitter/Variance box, just use Lag)")
            
            log(f"       4. Click 'Start' in Clumsy")
            input("       >>> Press ENTER once Clumsy is running to continue test... <<<")
        else:
            log("[NET] Baseline: Ensure Clumsy is STOPPED/PAUSED.")
            
    else:
        # Linux: Use tc netem
        # Clean existing first
        subprocess.run(f"tc qdisc del dev {INTERFACE} root", shell=True, 
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        cmd = f"tc qdisc add dev {INTERFACE} root netem"
        if loss > 0:
            cmd += f" loss {loss}%"
        if delay > 0:
            cmd += f" delay {delay}ms"
            if jitter > 0:
                cmd += f" {jitter}ms"
                
        if loss > 0 or delay > 0:
            log(f"[NET] Executing: {cmd}")
            subprocess.run(cmd, shell=True, check=True)

def clean_netem():
    """Cleanup logic."""
    if not IS_WINDOWS:
        try:
            subprocess.run(f"tc qdisc del dev {INTERFACE} root", shell=True, 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass
    else:
        print("\n[REMINDER] Stop Clumsy or Reset settings before next test!\n")

def analyze_results(csv_file, label):
    if not os.path.exists(csv_file):
        log(f"[ERR] CSV file {csv_file} not found. Cannot analyze.")
        return
    
    packets_received = 0
    duplicate_count = 0
    gap_count = 0
    total_cpu_ms = 0.0
    
    try:
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            reader.fieldnames = [name.strip() for name in reader.fieldnames]
            
            for row in reader:
                packets_received += 1
                if int(row.get('duplicate_flag', 0)) == 1:
                    duplicate_count += 1
                if int(row.get('gap_flag', 0)) == 1:
                    gap_count += 1
                total_cpu_ms += float(row.get('cpu_ms_per_report', 0.0))

        if packets_received > 0:
            duplicate_rate = (duplicate_count / packets_received)
            avg_cpu_ms = total_cpu_ms / packets_received
        else:
            duplicate_rate = 0.0
            avg_cpu_ms = 0.0

        print(f"\n--- RESULTS: {label} ---")
        print(f"{'packets_received':<25} : {packets_received}")
        print(f"{'duplicate_rate':<25} : {duplicate_rate:.2%}")
        print(f"{'sequence_gap_count':<25} : {gap_count}")
        print(f"{'cpu_ms_per_report':<25} : {avg_cpu_ms:.3f} ms")
        print("-" * 40 + "\n")

    except Exception as e:
        log(f"[ERR] Failed to parse CSV: {e}")

def run_test(scenario_name, interval, loss, delay, jitter, tshark_bin, interface_id):
    log(f"\n{'='*10} SCENARIO: {scenario_name} | Interval: {interval}s {'='*10}")
    
    csv_file = f"results_{scenario_name}_{interval}s.csv"
    pcap_file = f"trace_{scenario_name}_{interval}s.pcap"
    
    if os.path.exists(csv_file): os.remove(csv_file)
    if os.path.exists(pcap_file): os.remove(pcap_file)

    set_netem(loss, delay, jitter)

    # --- START CAPTURE ---
    cap_proc = None
    if tshark_bin:
        log(f"[PROC] Starting TShark Capture...")
        # On Windows, interface_id is a number string. On Linux, it's 'lo'
        cmd = [tshark_bin, "-i", interface_id, "-f", f"udp port {SERVER_PORT}", "-w", pcap_file]
        # Silence output
        cap_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3) 
    else:
        log("[WARN] TShark not found. Skipping PCAP.")

    # --- START SERVER ---
    log("[PROC] Starting Server...")
    cflags = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0
    server_cmd = [sys.executable, SERVER_SCRIPT, "--host", SERVER_IP, "--port", str(SERVER_PORT), "--csv", csv_file]
    server_proc = subprocess.Popen(server_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, creationflags=cflags)
    time.sleep(1)

    # --- START CLIENT ---
    log(f"[PROC] Starting Client (Interval: {interval}s)...")
    client_cmd = [sys.executable, CLIENT_SCRIPT, "--host", SERVER_IP, "--port", str(SERVER_PORT), "--interval", str(interval)]
    client_proc = subprocess.Popen(client_cmd, creationflags=cflags)

    # Wait
    try:
        wait_time = max(TEST_DURATION, interval * 4 + 10)
        log(f"[WAIT] Running for {wait_time}s...")
        client_proc.wait(timeout=wait_time)
    except subprocess.TimeoutExpired:
        if IS_WINDOWS:
            # Force kill tree on Windows
            subprocess.run(f"taskkill /F /T /PID {client_proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            client_proc.terminate()

    # --- CLEANUP ---
    if IS_WINDOWS:
        subprocess.run(f"taskkill /F /T /PID {server_proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if cap_proc:
            subprocess.run(f"taskkill /F /T /PID {cap_proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Prompt user to stop Clumsy if it was used
        if loss > 0 or delay > 0:
            clean_netem()
    else:
        server_proc.terminate()
        if cap_proc: cap_proc.terminate()
        clean_netem()

    log("[DONE] Scenario complete.")
    analyze_results(csv_file, f"{scenario_name}_{interval}s")

if __name__ == "__main__":
    check_requirements()
    tshark_bin = get_tshark_path()
    
    # Interface Selection logic
    if IS_WINDOWS:
        target_interface = select_interface_windows(tshark_bin)
    else:
        target_interface = "lo"

    try:
        # 1. Baseline
        for interval in [1, 5, 30]:
            run_test("baseline", interval=interval, loss=0, delay=0, jitter=0, 
                     tshark_bin=tshark_bin, interface_id=target_interface)

        # 2. Loss Scenarios (5%)
        run_test("loss_5pct", interval=1, loss=5, delay=0, jitter=0, 
                 tshark_bin=tshark_bin, interface_id=target_interface)

        # 3. Jitter
        run_test("jitter_test", interval=1, loss=0, delay=100, jitter=10, 
                 tshark_bin=tshark_bin, interface_id=target_interface)

        print("\nAll experiments finished.")

    except KeyboardInterrupt:
        print("\n[STOP] Interrupted.")
        clean_netem()