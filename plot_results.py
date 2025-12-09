import pandas as pd
import matplotlib.pyplot as plt
import glob
import os

def plot_bytes_vs_interval():
    # Load baseline CSVs for different intervals
    files = glob.glob("results_baseline_*s.csv")
    data = []
    
    for f in files:
        # Extract interval from filename (e.g., results_baseline_1s.csv)
        interval = int(f.split('_')[-1].replace('s.csv', ''))
        df = pd.read_csv(f)
        
        # Calculate Total Bytes per Report
        # Header (12) + Payload (20) = 32 bytes (Fixed for Project 1)
        # If your payload is variable, you'd need to calculate this dynamically.
        avg_bytes = 32 
        
        data.append({'Interval': interval, 'BytesPerReport': avg_bytes})
    
    if not data:
        print("No baseline CSV files found for plotting.")
        return

    df_plot = pd.DataFrame(data).sort_values('Interval')
    
    plt.figure(figsize=(8, 5))
    plt.plot(df_plot['Interval'], df_plot['BytesPerReport'], marker='o', linestyle='-')
    plt.title('Bytes per Report vs Reporting Interval')
    plt.xlabel('Reporting Interval (seconds)')
    plt.ylabel('Bytes per Report')
    plt.grid(True)
    plt.savefig('plot_bytes_vs_interval.png')
    print("Generated plot_bytes_vs_interval.png")

def plot_duprate_vs_loss():
    # Load loss scenario CSVs
    # You might need to run experiments with 0%, 2%, 5%, 10% loss to get a line
    # For now, we look for patterns like 'results_loss_*pct.csv'
    files = glob.glob("results_loss_*pct.csv")
    # Add baseline (0% loss)
    if os.path.exists("results_baseline_1s.csv"):
        files.append("results_baseline_1s.csv")
        
    data = []
    
    for f in files:
        df = pd.read_csv(f)
        total_packets = len(df)
        if total_packets == 0: continue
        
        # Determine loss % from filename
        if "baseline" in f:
            loss = 0
        else:
            # Extract loss from filename (e.g. results_loss_5pct.csv)
            try:
                loss = int(f.split('_')[-1].replace('pct.csv', ''))
            except:
                loss = 5 # Default fallback

        # Calculate Duplicate Rate
        dup_count = df['duplicate_flag'].sum()
        dup_rate = dup_count / total_packets
        
        data.append({'Loss': loss, 'DuplicateRate': dup_rate})

    if not data:
        print("No loss experiment CSV files found.")
        return

    df_plot = pd.DataFrame(data).sort_values('Loss')
    
    plt.figure(figsize=(8, 5))
    plt.plot(df_plot['Loss'], df_plot['DuplicateRate'], marker='x', color='r')
    plt.title('Duplicate Rate vs Packet Loss')
    plt.xlabel('Packet Loss (%)')
    plt.ylabel('Duplicate Rate')
    plt.grid(True)
    plt.savefig('plot_duprate_vs_loss.png')
    print("Generated plot_duprate_vs_loss.png")

if __name__ == "__main__":
    plot_bytes_vs_interval()
    plot_duprate_vs_loss()