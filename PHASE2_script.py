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
TEST_DURATION = 65 
RUNS_PER_SCENARIO = 5  # REQUIRED: 5 repetitions per measurement

SERVER_SCRIPT = "server.py"
CLIENT_SCRIPT = "client.py"

# Detect OS
IS_WINDOWS = platform.system() == "Windows"
INTERFACE = "lo" if not IS_WINDOWS else None 

# === Protocol Constants ===
# Header 12 bytes
HEADER_SIZE = 12

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

def analyze_single_run(csv_file):
    """Parses a single CSV run and calculates metrics."""
    if not os.path.exists(csv_file):
        log(f"[ERR] CSV file {csv_file} not found.")
        return None
    
    rows = []
    try:
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            reader.fieldnames = [name.strip() for name in reader.fieldnames]
            for r in reader:
                rows.append(r)
    except Exception as e:
        log(f"[ERR] Failed to read CSV: {e}")
        return None

    if not rows:
        return None

    # === REORDERING LOGIC (Requirement: Reorder by timestamp for analysis) ===
    # Sort rows by client timestamp (send time)
    rows.sort(key=lambda x: int(x.get('timestamp', 0)))

    packets_received = len(rows)
    duplicate_count = 0
    gap_count = 0
    total_cpu_ms = 0.0
    latencies = []
    
    # Calculate bytes per report (Header + Payload)
    # We estimate based on standard packet size for this project.
    # Header (12) + 5 floats (20) = 32 bytes usually.
    # To be precise, one could inspect packet size, but fixed is acceptable for now.
    bytes_per_report = 32 

    previous_seq = -1

    for row in rows:
        seq = int(row.get('seq', -1))
        
        # Check duplicates (in sorted order)
        if seq == previous_seq:
            duplicate_count += 1
        elif previous_seq != -1 and seq > previous_seq + 1:
            gap_count += (seq - previous_seq - 1)
        
        previous_seq = seq

        total_cpu_ms += float(row.get('cpu_ms_per_report', 0.0))

        # Latency Calculation
        try:
            ts_sent_masked = int(row.get('timestamp', 0))
            arrival_full = float(row.get('arrival_time', 0))
            arrival_masked = int(arrival_full * 1000) & 0xFFFFFFFF
            diff = arrival_masked - ts_sent_masked
            if diff < -1000000000: diff += 2**32 # Wrap handling
            if diff >= 0: latencies.append(diff)
        except ValueError:
            pass

    avg_latency = statistics.mean(latencies) if latencies else 0.0
    duplicate_rate = (duplicate_count / packets_received) if packets_received else 0.0
    avg_cpu_ms = (total_cpu_ms / packets_received) if packets_received else 0.0

    return {
        "packets_received": packets_received,
        "avg_latency": avg_latency,
        "duplicate_rate": duplicate_rate,
        "gap_count": gap_count,
        "cpu_ms": avg_cpu_ms,
        "bytes_per_report": bytes_per_report
    }

def print_aggregated_stats(scenario_name, results_list):
    """Calculates and prints Min/Median/Max for the 5 runs."""
    if not results_list:
        print(f"[ERR] No results for {scenario_name}")
        return

    # Extract lists of metrics
    latencies = [r["avg_latency"] for r in results_list]
    dup_rates = [r["duplicate_rate"] for r in results_list]
    gaps = [r["gap_count"] for r in results_list]
    bytes_rep = [r["bytes_per_report"] for r in results_list]

    print(f"\n{'='*20} RESULTS SUMMARY: {scenario_name} ({len(results_list)} runs) {'='*20}")
    print(f"{'Metric':<25} | {'Min':<10} | {'Median':<10} | {'Max':<10}")
    print("-" * 65)
    
    print(f"{'Avg Latency (ms)':<25} | {min(latencies):<10.3f} | {statistics.median(latencies):<10.3f} | {max(latencies):<10.3f}")
    print(f"{'Duplicate Rate':<25} | {min(dup_rates):<10.2%} | {statistics.median(dup_rates):<10.2%} | {max(dup_rates):<10.2%}")
    print(f"{'Gap Count':<25} | {min(gaps):<10} | {statistics.median(gaps):<10} | {max(gaps):<10}")
    print(f"{'Bytes/Report':<25} | {statistics.median(bytes_rep):<10} (Fixed)")
    print("-" * 65 + "\n")

    return statistics.median(latencies)

def run_scenario_batch(scenario_name, interval, loss, delay, jitter, tshark_bin, interface_id, batch_size=5):
    """Runs a scenario 5 times and aggregates results."""
    run_results = []
    
    set_netem(loss, delay, jitter)

    for i in range(1, RUNS_PER_SCENARIO + 1):
        log(f"--- Starting Run {i}/{RUNS_PER_SCENARIO} for {scenario_name} ---")
        
        csv_file = f"results_{scenario_name}_{interval}s_run{i}.csv"
        pcap_file = f"trace_{scenario_name}_{interval}s_run{i}.pcap"
        
        # Cleanup previous
        if os.path.exists(csv_file): os.remove(csv_file)
        if os.path.exists(pcap_file): os.remove(pcap_file)

        # 1. Capture
        cap_proc = None
        if tshark_bin:
            cmd = [tshark_bin, "-i", interface_id, "-f", f"udp port {SERVER_PORT}", "-w", pcap_file]
            cap_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2) 

        # 2. Server
        cflags = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0
        server_cmd = [sys.executable, SERVER_SCRIPT, "--host", SERVER_IP, "--port", str(SERVER_PORT), "--csv", csv_file]
        server_proc = subprocess.Popen(server_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, creationflags=cflags)
        time.sleep(1)

        # 3. Client
        # Added --batch argument
        client_cmd = [sys.executable, CLIENT_SCRIPT, "--host", SERVER_IP, "--port", str(SERVER_PORT), 
                      "--interval", str(interval), "--batch", str(batch_size)]
        client_proc = subprocess.Popen(client_cmd, creationflags=cflags)

        # 4. Wait
        try:
            client_proc.wait(timeout=TEST_DURATION)
        except subprocess.TimeoutExpired:
            if IS_WINDOWS:
                subprocess.run(f"taskkill /F /T /PID {client_proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                client_proc.terminate()

        # 5. Cleanup Processes
        if IS_WINDOWS:
            subprocess.run(f"taskkill /F /T /PID {server_proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if cap_proc: subprocess.run(f"taskkill /F /T /PID {cap_proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            server_proc.terminate()
            if cap_proc: cap_proc.terminate()
        
        # 6. Analyze this specific run
        stats = analyze_single_run(csv_file)
        if stats:
            run_results.append(stats)
            print(f"   Run {i} Stats: Latency={stats['avg_latency']:.2f}ms, Gaps={stats['gap_count']}")
        else:
            print(f"   Run {i} Failed to produce stats.")
        
        time.sleep(1) # Cooldown between runs

    # Cleanup Netem only after ALL runs for this scenario are done
    if loss > 0 or delay > 0:
        clean_netem()

    return print_aggregated_stats(f"{scenario_name}_{interval}s", run_results)

if __name__ == "__main__":
    check_requirements()
    tshark_bin = get_tshark_path()
    if IS_WINDOWS:
        target_interface = select_interface_windows(tshark_bin)
    else:
        target_interface = "lo"

    try:
        baseline_latency_1s = 0.0

        # === 1. Baseline Suite (1s, 5s, 30s) ===
        print(f"\n{'='*20} STARTING BASELINE SUITE (1s, 5s, 30s) {'='*20}")

        # Interval 1s
        val = run_scenario_batch("baseline", interval=1, loss=0, delay=0, jitter=0, 
                                 tshark_bin=tshark_bin, interface_id=target_interface)
        if val: baseline_latency_1s = val

        # Interval 5s
        run_scenario_batch("baseline", interval=5, loss=0, delay=0, jitter=0, 
                           tshark_bin=tshark_bin, interface_id=target_interface)

        # Interval 30s
        run_scenario_batch("baseline", interval=30, loss=0, delay=0, jitter=0, 
                           tshark_bin=tshark_bin, interface_id=target_interface)

        # === 2. Loss 5% ===
        print(f"\n{'='*20} STARTING LOSS SCENARIO {'='*20}")
        run_scenario_batch("loss_5pct", interval=1, loss=5, delay=0, jitter=0, 
                           tshark_bin=tshark_bin, interface_id=target_interface)

        # === 3. Jitter/Delay Test ===
        print(f"\n{'='*20} STARTING JITTER SCENARIO {'='*20}")
        test_latency_jitter = 0.0
        val = run_scenario_batch("jitter_test", interval=1, loss=0, delay=100, jitter=10, 
                                 tshark_bin=tshark_bin, interface_id=target_interface)
        if val: test_latency_jitter = val

        # === FINAL ACCEPTANCE CHECK ===
        print("\n" + "="*50)
        print("LATENCY IMPACT ANALYSIS (100ms DELAY TEST)")
        print("="*50)
        print(f"Baseline Median Latency (1s): {baseline_latency_1s:8.3f} ms")
        print(f"Jitter Test Median Latency:   {test_latency_jitter:8.3f} ms")
        diff = test_latency_jitter - baseline_latency_1s
        print("-" * 50)
        print(f"OBSERVED DELAY INCREASE:      {diff:8.3f} ms")
        
        if 80.0 <= diff <= 120.0:
             print(f"RESULT: [PASS] Matches target 100ms delay")
        else:
             print(f"RESULT: [FAIL] Deviation > 20ms from target")
        print("="*50 + "\n")

    except KeyboardInterrupt:
        print("\n[STOP] Interrupted.")
        clean_netem()