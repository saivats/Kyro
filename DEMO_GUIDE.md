# KYRO faculty demonstration

Allow about five minutes. Use only fictional information. Run `setup.bat` once, then `start.bat` and open http://127.0.0.1:5000. Wait for “System ready”.

1. In **Doctor workspace**, edit Demo doctor B (cardiology). Set capacity to **1** and keep “Accept new cases” selected. Start with an empty demonstration database.
2. In **Case intake**, load **Cardiology transfer**, label it **Slot holder**, confirm fictional data and submit. Inspect all four scores and the five largest signed TreeSHAP contributions. Point out that the symptom description and oxygen reading are available to the reviewer, but neither enters the model.
3. Select **Medium** as the human-confirmed severity and confirm cardiology. The case is assigned to Demo doctor B. Create two more cardiology cases, **Earlier waiting** and **Priority waiting**. Confirm them as **Low** and **Critical**, respectively. You may override any model output for this simulation.
4. Both new cases wait. Start and complete **Slot holder**. **Priority waiting** receives the released slot first. The older Low case stays in the queue. Refresh, then open the Completed filter to show the earlier treatment.
5. Show the doctor's workload, overview counts, event history and historical confusion matrix. For another AI input, try **Respiratory review** and compare the actual outputs. Severity and specialty are separate decisions.

**Viva points.** The model produces four uncalibrated scores. TreeSHAP decomposes a class's raw margin. A positive contribution to Low increases the model's preference for Low. SQLite serializes review, assignment and release using one write transaction. Intake retries use a unique request ID and payload fingerprint. Priority uses confirmed severity descending, then intake sequence ascending. Eligible doctors are ordered by occupied fraction, then stable ID.

**Reset.** Stop the server. From the repo root run `.\.venv\Scripts\python.exe demo.py --reset-demo` and type `RESET KYRO`. This clears fictional records and restores the original roster. The command checks the default path and database identity and rejects custom database paths.
