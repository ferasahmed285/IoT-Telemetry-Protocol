import subprocess
import time
import os
import sys
import platform
import shutil
import csv
import statistics

# === Configuration ===
SERVER_IP = "127.0.0.1"
SERVER_PORT = 5005
TEST_DURATION = 70 

SERVER_SCRIPT = "server.py"
CLIENT_SCRIPT = "client.py"

# Detect OS
IS_WINDOWS = platform.system() == "Windows"
INTERFACE = "lo" if not IS_WINDOWS else None 

# === Protocol Constants ===
# Header 12 bytes + Payload 20 bytes = 32 bytes total
PACKET_SIZE_BYTES = 12 + 20 

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def check_requirements():
    if not IS_WINDOWS and os.geteuid() != 0:
        log("[ERR] On Linux/WSL, run as root (sudo) for 'netem'.")
        sys.exit(1)

def get_tshark_path():
    tshark = shutil.which("tshark")
    if tshark: return tshark
    if IS_WINDOWS:
        paths = [r"C:\Program Files\Wireshark\tshark.exe", r"C:\Program Files (x86)\Wireshark\tshark.exe"]
        for p in paths:
            if os.path.exists(p): return p
    return None

def select_interface_windows(tshark_bin):
    if not tshark_bin: return "1"
    print("\n" + "="*60)
    print("WINDOWS NETWORK INTERFACE SELECTION")
    print("="*60)
    try:
        subprocess.run([tshark_bin, "-D"])
    except Exception as e:
        print(f"Error listing interfaces: {e}")
        return "1"
    print("-" * 60)
    choice = input("Enter Interface Number (e.g., 4): ").strip()
    return choice

def set_netem(loss=0, delay=0, jitter=0):
    if IS_WINDOWS:
        if loss > 0 or delay > 0:
            log(f"\n[WARN] Windows Detected. Automation paused for setup.")
            log(f"       >>> ACTION REQUIRED: ENABLE CLUMSY NOW <<<")
            log(f"       1. Open Clumsy")
            log(f"       2. Filter: udp and udp.DstPort == {SERVER_PORT}")
            if loss > 0: log(f"       3. Check 'Drop' -> Set to {loss}.0 %")
            if delay > 0: 
                log(f"       3. Check 'Lag' -> Set to {delay} ms")
            log(f"       4. Click 'Start' in Clumsy")
            input("       >>> Press ENTER once Clumsy is running... <<<")
    else:
        subprocess.run(f"tc qdisc del dev {INTERFACE} root", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cmd = f"tc qdisc add dev {INTERFACE} root netem"
        if loss > 0: cmd += f" loss {loss}%"
        if delay > 0:
            cmd += f" delay {delay}ms"
            if jitter > 0: cmd += f" {jitter}ms"
        if loss > 0 or delay > 0:
            log(f"[NET] Executing: {cmd}")
            subprocess.run(cmd, shell=True, check=True)

def clean_netem():
    if not IS_WINDOWS:
        try:
            subprocess.run(f"tc qdisc del dev {INTERFACE} root", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass
    else:
        print("\n[REMINDER] Stop Clumsy before next test!\n")

def analyze_results(csv_file, label):
    if not os.path.exists(csv_file):
        log(f"[ERR] CSV file {csv_file} not found.")
        return {}
    
    packets_received = 0
    duplicate_count = 0
    gap_count = 0
    total_cpu_ms = 0.0
    latencies = []
    
    try:
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            reader.fieldnames = [name.strip() for name in reader.fieldnames]
            
            for row in reader:
                packets_received += 1
                if int(row.get('duplicate_flag', 0)) == 1: duplicate_count += 1
                if int(row.get('gap_flag', 0)) == 1: gap_count += 1
                total_cpu_ms += float(row.get('cpu_ms_per_report', 0.0))

                # === COMPUTE LATENCY WITH TRUNCATED TIMESTAMPS ===
                try:
                    # Client sent: 32-bit truncated millis
                    ts_sent_masked = int(row.get('timestamp', 0))
                    
                    # Server recorded: Full float seconds
                    arrival_full = float(row.get('arrival_time', 0))
                    
                    # Convert Server time to same 32-bit masked millis format
                    arrival_masked = int(arrival_full * 1000) & 0xFFFFFFFF
                    
                    # Simple Difference
                    diff = arrival_masked - ts_sent_masked
                    
                    # Handle Wrap-around (unlikely in short test, but good safety)
                    # If diff is massive negative, it means arrival wrapped 0xFFFFFFFF
                    if diff < -1000000000:
                        diff += 2**32
                        
                    if diff >= 0:
                        latencies.append(diff)
                        
                except ValueError:
                    pass

        if packets_received > 0:
            duplicate_rate = (duplicate_count / packets_received)
            avg_cpu_ms = total_cpu_ms / packets_received
        else:
            duplicate_rate = 0.0
            avg_cpu_ms = 0.0
            
        avg_latency = statistics.mean(latencies) if latencies else 0.0

        print(f"\n--- RESULTS: {label} ---")
        print(f"{'packets_received':<25} : {packets_received}")
        print(f"{'duplicate_rate':<25} : {duplicate_rate:.2%}")
        print(f"{'sequence_gap_count':<25} : {gap_count}")
        print(f"{'avg_latency':<25} : {avg_latency:.3f} ms") 
        print(f"{'cpu_ms_per_report':<25} : {avg_cpu_ms:.3f} ms")
        print("-" * 40 + "\n")

        return {"avg_latency": avg_latency, "packets_received": packets_received}

    except Exception as e:
        log(f"[ERR] Failed to parse CSV: {e}")
        return {}

def run_test(scenario_name, interval, loss, delay, jitter, tshark_bin, interface_id):
    log(f"\n{'='*10} SCENARIO: {scenario_name} | Interval: {interval}s {'='*10}")
    
    csv_file = f"results_{scenario_name}_{interval}s.csv"
    pcap_file = f"trace_{scenario_name}_{interval}s.pcap"
    
    if os.path.exists(csv_file): os.remove(csv_file)
    if os.path.exists(pcap_file): os.remove(pcap_file)

    set_netem(loss, delay, jitter)

    # Capture
    cap_proc = None
    if tshark_bin:
        cmd = [tshark_bin, "-i", interface_id, "-f", f"udp port {SERVER_PORT}", "-w", pcap_file]
        cap_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3) 

    # Server
    cflags = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0
    server_cmd = [sys.executable, SERVER_SCRIPT, "--host", SERVER_IP, "--port", str(SERVER_PORT), "--csv", csv_file]
    server_proc = subprocess.Popen(server_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, creationflags=cflags)
    time.sleep(1)

    # Client
    client_cmd = [sys.executable, CLIENT_SCRIPT, "--host", SERVER_IP, "--port", str(SERVER_PORT), "--interval", str(interval)]
    client_proc = subprocess.Popen(client_cmd, creationflags=cflags)

    try:
        wait_time = max(TEST_DURATION, interval * 4 + 10)
        log(f"[WAIT] Running for {wait_time}s...")
        client_proc.wait(timeout=wait_time)
    except subprocess.TimeoutExpired:
        if IS_WINDOWS:
            subprocess.run(f"taskkill /F /T /PID {client_proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            client_proc.terminate()

    if IS_WINDOWS:
        subprocess.run(f"taskkill /F /T /PID {server_proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if cap_proc: subprocess.run(f"taskkill /F /T /PID {cap_proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if loss > 0 or delay > 0: clean_netem()
    else:
        server_proc.terminate()
        if cap_proc: cap_proc.terminate()
        clean_netem()

    log("[DONE] Scenario complete.")
    return analyze_results(csv_file, f"{scenario_name}_{interval}s")

if __name__ == "__main__":
    check_requirements()
    tshark_bin = get_tshark_path()
    if IS_WINDOWS:
        target_interface = select_interface_windows(tshark_bin)
    else:
        target_interface = "lo"

    try:
        baseline_latency = 0.0
        test_latency = 0.0

        # 1. Baseline
        for interval in [1, 5, 30]:
            stats = run_test("baseline", interval=interval, loss=0, delay=0, jitter=0, 
                             tshark_bin=tshark_bin, interface_id=target_interface)
            if interval == 1 and stats:
                baseline_latency = stats.get("avg_latency", 0.0)

        # 2. Loss
        run_test("loss_5pct", interval=1, loss=5, delay=0, jitter=0, 
                 tshark_bin=tshark_bin, interface_id=target_interface)

        # 3. Jitter (Delay)
        stats = run_test("jitter_test", interval=1, loss=0, delay=100, jitter=10, 
                         tshark_bin=tshark_bin, interface_id=target_interface)
        if stats:
            test_latency = stats.get("avg_latency", 0.0)

        # === FINAL COMPARISON ===
        print("\n" + "="*50)
        print("LATENCY IMPACT ANALYSIS (100ms DELAY TEST)")
        print("="*50)
        print(f"1. Baseline Latency (1s Interval):  {baseline_latency:8.3f} ms")
        print(f"2. Jitter Test Latency (100ms+):    {test_latency:8.3f} ms")
        diff = test_latency - baseline_latency
        print("-" * 50)
        print(f"OBSERVED DELAY INCREASE:            {diff:8.3f} ms")
        
        if 80.0 <= diff <= 120.0:
             print(f"RESULT: [PASS] matches target 100ms")
        else:
             print(f"RESULT: [FAIL] Deviation > 20ms from 100ms target")
        print("="*50 + "\n")

    except KeyboardInterrupt:
        print("\n[STOP] Interrupted.")
        clean_netem()