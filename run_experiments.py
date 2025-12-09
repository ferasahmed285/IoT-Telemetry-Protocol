import subprocess
import time
import os
import sys
import platform
import shutil
import re

# === Configuration ===
SERVER_IP = "127.0.0.1"  # Best for Clumsy
SERVER_PORT = 5005
TEST_DURATION = 70 

SERVER_SCRIPT = "server.py"
CLIENT_SCRIPT = "client.py"
IS_WINDOWS = platform.system() == "Windows"

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def get_tshark_path():
    """Finds TShark executable."""
    tshark = shutil.which("tshark")
    if tshark: return tshark
    paths = [r"C:\Program Files\Wireshark\tshark.exe", r"C:\Program Files (x86)\Wireshark\tshark.exe"]
    for p in paths:
        if os.path.exists(p): return p
    return None

def select_interface_interactive(tshark_bin):
    """Lists interfaces and forces user to pick the Loopback one."""
    if not IS_WINDOWS: return "lo"

    print("\n" + "="*60)
    print("WINDOWS NETWORK INTERFACE SELECTION")
    print("="*60)
    
    # Run tshark -D to list interfaces
    try:
        # We print this so you can choose, but we hide the command itself
        result = subprocess.run([tshark_bin, "-D"], capture_output=True, text=True)
        print(result.stdout)
    except Exception as e:
        print(f"Error running TShark: {e}")
        return "1"

    print("-" * 60)
    print("Enter the NUMBER for 'Adapter for loopback traffic capture'.")
    print("-" * 60)
    
    choice = input("Enter Interface Number (e.g. 10): ").strip()
    return choice

def set_netem(loss=0, delay=0, jitter=0):
    if IS_WINDOWS:
        if loss > 0 or delay > 0:
            log(f"[WARN] Windows Detected. Script pausing...")
            log(f"       >>> PLEASE ENABLE CLUMSY NOW <<<")
            log(f"       Filter: udp and udp.DstPort == 5005")
            log(f"       Loss: {loss}%, Delay: {delay}ms")
            input("       Press ENTER once Clumsy is running...")
        return
    # Linux logic omitted for brevity as you are on Windows

def run_test(scenario_name, interval, loss, delay, jitter, tshark_bin, interface):
    log(f"\n{'='*10} SCENARIO: {scenario_name} | Interval: {interval}s {'='*10}")
    
    csv_file = f"results_{scenario_name}_{interval}s.csv"
    pcap_file = f"trace_{scenario_name}_{interval}s.pcap"
    
    if os.path.exists(csv_file): os.remove(csv_file)
    if os.path.exists(pcap_file): os.remove(pcap_file)

    set_netem(loss, delay, jitter)

    # --- START CAPTURE ---
    cap_proc = None
    if tshark_bin:
        cmd = [tshark_bin, "-i", interface, "-f", f"udp port {SERVER_PORT}", "-w", pcap_file]
        log(f"[PROC] Starting TShark Capture (Interface #{interface})...")
        # SILENCE THE EXECUTABLE OUTPUT
        cap_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3) 
    else:
        log("[WARN] TShark not found.")

    # --- START SERVER ---
    log("[PROC] Starting Server...")
    cflags = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0
    server_cmd = [sys.executable, SERVER_SCRIPT, "--host", SERVER_IP, "--port", str(SERVER_PORT), "--csv", csv_file]
    # Server output is suppressed (DEVNULL)
    server_proc = subprocess.Popen(server_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, creationflags=cflags)
    time.sleep(1)

    # --- START CLIENT ---
    log(f"[PROC] Starting Client (Interval: {interval}s)...")
    client_cmd = [sys.executable, CLIENT_SCRIPT, "--host", SERVER_IP, "--port", str(SERVER_PORT), "--interval", str(interval)]
    # Client output is SHOWN so you can see progress
    client_proc = subprocess.Popen(client_cmd, creationflags=cflags)

    # Wait
    try:
        wait_time = max(TEST_DURATION, interval * 4 + 10)
        log(f"[WAIT] Running for {wait_time}s...")
        client_proc.wait(timeout=wait_time)
    except subprocess.TimeoutExpired:
        if IS_WINDOWS:
            subprocess.run(f"taskkill /F /T /PID {client_proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            client_proc.terminate()

    # --- CLEANUP ---
    if IS_WINDOWS:
        subprocess.run(f"taskkill /F /T /PID {server_proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if cap_proc:
            subprocess.run(f"taskkill /F /T /PID {cap_proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        server_proc.terminate()
        if cap_proc: cap_proc.terminate()

    log("[DONE] Scenario complete.")

if __name__ == "__main__":
    tshark_bin = get_tshark_path()
    
    # Run selection ONCE
    if tshark_bin:
        selected_interface = select_interface_interactive(tshark_bin)
    else:
        selected_interface = "1"
        print("ERROR: TShark not found. PCAP generation disabled.")

    try:
        # 1. Baseline
        for interval in [1, 5, 30]:
            run_test("baseline", interval=interval, loss=0, delay=0, jitter=0, 
                     tshark_bin=tshark_bin, interface=selected_interface)

        # 2. Loss Scenarios (2% and 5%)
        # --- NEW 2% LOSS TEST ---
        run_test("loss_2pct", interval=1, loss=2, delay=0, jitter=0, 
                 tshark_bin=tshark_bin, interface=selected_interface)

        # 5% LOSS TEST
        run_test("loss_5pct", interval=1, loss=5, delay=0, jitter=0, 
                 tshark_bin=tshark_bin, interface=selected_interface)

        # 3. Jitter
        run_test("jitter_test", interval=1, loss=0, delay=100, jitter=10, 
                 tshark_bin=tshark_bin, interface=selected_interface)

        print("\nAll experiments finished.")

    except KeyboardInterrupt:
        print("\n[STOP] Interrupted.")