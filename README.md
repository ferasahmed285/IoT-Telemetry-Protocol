````markdown
# IoT Telemetry Protocol

**Course:** CSE361 - Computer Networks  
**Phase:** 2 (Feature Completion & Tests)   
**Repository:** [ferasahmed285/IoT-Telemetry-Protocol](https://github.com/ferasahmed285/IoT-Telemetry-Protocol)

## 📹 Project Demo Video
**[in phase 3 submission]**

---

## 📂 Project Overview
This repository contains the design and implementation of **IoTStream v1**, a custom application-layer protocol running over UDP. It is designed for constrained IoT sensors to report telemetry data efficiently under varying network conditions, such as packet loss and jitter.

### Phase 2 Features
* **Custom Binary Protocol:** Compact 12-byte header (<= 12 bytes).
* **Batching Support:** Optional aggregation of N sensor readings into a single packet.
* **Automated Experiments:** Reproducible scripts using Linux `netem` to simulate Loss and Jitter.
* **Analysis Tools:** Post-processing scripts to calculate latency, detect gaps, and generate CSV reports.

---

## 📁 File Structure

| File | Description |
| :--- | :--- |
| `Mini-RFC.pdf` | Protocol specification document (Header format, FSM, logic). |
| `PHASE2_script.py` | **Main Automation Script.** Runs all 5 repetitions of Baseline, Loss, and Jitter scenarios. |
| `server.py` | The Collector. Parses packets, detects gaps/duplicates, and logs metrics to CSV. |
| `client.py` | The Sensor. Generates readings, handles batching, and packs binary headers. |
| `plot_results.py` | Generates required graphs: Bytes/Report, Duplicate Rate, Latency. |
| `README.md` | This file. |

---

## ⚙️ Requirements & Prerequisites

* **Python 3.x**
* **OS:** Linux is highly recommended for automated `netem` tests (e.g., Ubuntu VM or WSL2).
* **Tools:**
    * `sudo` privileges (Required to configure network interfaces via `tc`).
    * `tshark` / Wireshark (Optional, for PCAP capture validation).

---

## 🚀 How to Run (Automated Suite)

The `PHASE2_script.py` script is the primary entry point. It automates the entire test suite required for the project deliverables.

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/ferasahmed285/IoT-Telemetry-Protocol.git](https://github.com/ferasahmed285/IoT-Telemetry-Protocol.git)
    cd IoT-Telemetry-Protocol
    ```

2.  **Run with root privileges** (required for `tc` network emulation):
    ```bash
    sudo python3 PHASE2_script.py
    ```

**What this script does:**
* **Sets up NetEm:** Automatically applies Delay, Jitter, or Loss rules to the loopback interface.
* **Iterates:** Runs **5 repetitions** for each scenario (Baseline, Loss 5%, Jitter) as required.
* **Logs:** Generates `.csv` logs and `.pcap` traces for every run.
* **Analyzes:** Computes Min/Median/Max latency, duplicate rates, and gap counts.

---

## 🛠 How to Run (Manual Mode)

If you wish to run the client and server individually for debugging:

### 1. Start the Server
```bash
python3 server.py --host 0.0.0.0 --port 5005 --csv server_log.csv
````

  * **Server Responsibilities:** Parses the 12-byte header, reorders timestamps for analysis, detects sequence gaps, and logs `cpu_ms_per_report`.

### 2\. Start the Client

```bash
python3 client.py --host 127.0.0.1 --port 5005 --device 1001 --interval 1 --batch 5
```

  * **Parameters:**
      * `--interval`: Reporting frequency (1s, 5s, 30s).
      * `--batch`: Number of sensor readings per packet (Default: 5).

-----

## 🧠 Design Details

### Header Format

We utilize Python's `struct` library (`!BBHHIBB`) to create a strictly packed binary header of exactly **12 Bytes**.

| Field | Size | Description |
| :--- | :--- | :--- |
| **Version** | 1 Byte | Protocol Version (v1) |
| **MsgType** | 1 Byte | 0=INIT, 1=DATA, 2=HEARTBEAT |
| **DeviceID** | 2 Bytes | Unique Sensor ID |
| **SeqNum** | 2 Bytes | Sequence Number |
| **Timestamp** | 4 Bytes | 32-bit masked milliseconds |
| **BatchFlag** | 1 Byte | Number of readings in payload |
| **Checksum** | 1 Byte | Simple header checksum |

### Batching Strategy

The protocol supports configurable batching. By grouping N readings (default 5) into one packet, we significantly reduce the bytes-per-report overhead.

  * **Payload Limit:** 12 (Header) + (5 \* 4 Bytes) = 32 Bytes, well within the 200-byte limit.

-----

## 🧪 Reproducibility: NetEm Commands

To ensure experiments are reproducible, the script applies the following Linux `netem` commands:

| Scenario | Command Used | Acceptance Criteria |
| :--- | :--- | :--- |
| **Baseline** | `sudo tc qdisc del dev lo root` | \>= 99% delivery, ordered seq. |
| **Loss 5%** | `sudo tc qdisc add dev lo root netem loss 5%` | Server detects gaps, \< 1% dups. |
| **Jitter** | `sudo tc qdisc add dev lo root netem delay 100ms 10ms` | Correct reordering by timestamp. |

-----

## 📊 Phase 1 Baseline Results (Legacy)

*Included for reference to Phase 1 prototype performance.*

  * **Packets Sent/Received:** 60/60
  * **Delivery Rate:** 100%
  * **Sequence Integrity:** Pass (Continuous 1 -\> 60)

<!-- end list -->

```
```
