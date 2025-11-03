IoTStream v1 - Project Phase 1

This folder contains the Phase 1 prototype for the Computer Networks "IoT Telemetry Protocol" project. It includes the protocol design (Mini-RFC), a working prototype (client/server), and an automated test script.

Project Files:

Mini-RFC.pdf

ProjectProposal_IoTStream_v1.pdf

server.py

client.py

script.py

README.md (This file)

Requirements:
Python 3.x

How to Run the Baseline Test
To run the automated baseline test and get the results, execute the provided script. This script will automatically start the server, run the client for the full duration, and generate the required log files.

Open a terminal in the project directory.

Run the test script: python script.py

The script will run for approximately 65 seconds.

When complete, check the generated log files (server_log.txt and client_log.txt) to see the results.

Baseline Test Results
The following results were observed from the test run that generated server_log.txt and client_log.txt.

Metric: Total DATA packets sent Result: 60

Metric: Total DATA packets received Result: 60

Metric: Delivery Rate Result: 100%

Metric: Sequence Numbers Result: Continuous and in correct order (1 -> 60)

Result: Pass

Analysis: The system achieved 100% (60/60) packet delivery during the baseline (no impairment) test. All sequence numbers were received in the correct order. This result meets and exceeds the >=99% acceptance criteria.