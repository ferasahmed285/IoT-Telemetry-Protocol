import pandas as pd
import matplotlib.pyplot as plt
import glob
import os
import re

def plot_bytes_vs_interval():
    print("Generating 'Bytes per Report vs Interval' plot...")
    
    # Matches: results_baseline_1s.csv, results_baseline_5s.csv, etc.
    files = glob.glob("results_baseline_*s.csv")
    data = []
    
    for f in files:
        try:
            # Parse interval from filename (e.g. results_baseline_30s.csv)
            # Regex extracts the digits before 's.csv'
            match = re.search(r'_(\d+)s\.csv$', f)
            if match:
                interval = int(match.group(1))
                
                # Project spec: Header(12) + Payload(20) = 32 bytes
                # (You could also sum the bytes from the CSV if you logged packet size)
                avg_bytes = 32 
                
                data.append({'Interval': interval, 'BytesPerReport': avg_bytes})
        except Exception as e:
            print(f"Skipping {f}: {e}")
    
    if not data:
        print("[WARN] No baseline CSVs found. Run experiments first.")
        return

    df_plot = pd.DataFrame(data).sort_values('Interval')
    
    plt.figure(figsize=(10, 6))
    plt.plot(df_plot['Interval'], df_plot['BytesPerReport'], marker='o', linestyle='-', color='#1f77b4', linewidth=2)
    plt.title('Bytes per Report vs Reporting Interval')
    plt.xlabel('Reporting Interval (seconds)')
    plt.ylabel('Bytes per Report (Header + Payload)')
    plt.grid(True, linestyle='--', alpha=0.7)
    
    # Ensure all intervals are shown on X-axis
    plt.xticks(df_plot['Interval'])
    plt.ylim(0, max(df_plot['BytesPerReport']) * 1.2) # Add some headroom
    
    plt.savefig('plot_bytes_vs_interval.png')
    print(" -> Saved 'plot_bytes_vs_interval.png'")

def plot_duprate_vs_loss():
    print("Generating 'Duplicate Rate vs Loss' plot...")
    
    # 1. Find Loss Files (e.g. results_loss_2pct_1s.csv, results_loss_5pct_1s.csv)
    files = glob.glob("results_loss_*pct_*.csv")
    
    # 2. Add Baseline (0% Loss) if it exists
    if os.path.exists("results_baseline_1s.csv"):
        files.append("results_baseline_1s.csv")
        
    data = []
    for f in files:
        try:
            df = pd.read_csv(f)
            if len(df) == 0: continue
            
            # Determine Loss % from filename
            loss = 0
            if "loss" in f:
                # Regex to find 'Xpct'
                match = re.search(r'loss_(\d+)pct', f)
                if match:
                    loss = int(match.group(1))
            elif "baseline" in f:
                loss = 0
            
            # Calculate Duplicate Rate: (Count of Duplicate Flags / Total Packets)
            # Ensure 'duplicate_flag' column exists
            if 'duplicate_flag' in df.columns:
                dup_count = df['duplicate_flag'].sum()
                total_packets = len(df)
                dup_rate = dup_count / total_packets if total_packets > 0 else 0
                
                data.append({'Loss': loss, 'DuplicateRate': dup_rate})
            else:
                print(f"[WARN] Column 'duplicate_flag' missing in {f}")

        except Exception as e:
            print(f"Error processing {f}: {e}")

    if not data:
        print("[WARN] No data found for Loss plot.")
        return

    # Sort by Loss percentage
    df_plot = pd.DataFrame(data).sort_values('Loss')
    
    plt.figure(figsize=(10, 6))
    plt.plot(df_plot['Loss'], df_plot['DuplicateRate'], marker='s', linestyle='--', color='#d62728', linewidth=2)
    plt.title('Duplicate Rate vs Packet Loss')
    plt.xlabel('Packet Loss (%)')
    plt.ylabel('Duplicate Rate (Fraction)')
    plt.grid(True, linestyle='--', alpha=0.7)
    
    # Force integer ticks on X-axis
    plt.xticks(df_plot['Loss'])
    
    plt.savefig('plot_duprate_vs_loss.png')
    print(" -> Saved 'plot_duprate_vs_loss.png'")

if __name__ == "__main__":
    plot_bytes_vs_interval()
    plot_duprate_vs_loss()
    print("\nDone.")