# EdgeOps operating runbook

## Deployed AWS application

Open [EdgeOps on CloudFront](https://d3aum9pitkz6he.cloudfront.net) and sign in with an authorized Cognito operator's email address and password. If an operator forgets their password or their temporary password expires (after 1 day), the workspace owner sets a new temporary password; there is no self-service reset. The Sydney deployment uses a single shared synthetic fleet stored in DynamoDB. Dashboard actions change that shared state; coordinate before a reset or recovery demonstration.

External telemetry is accepted into SQS with HTTP 202 and processed asynchronously by the worker Lambda. Confirm resulting device sequences or processing counters before claiming delivery completed. See [AWS deployment](../guides/aws-deployment.md), [pipeline operation](../reference/ci-pipeline.md) and the [verified results](../reference/validation.md). The local commands and SQLite backup exercise below apply to local mode.

The final verified deployment is `0.3.0`. Jenkins builds #5, #6 and #8 successfully released it, restored the exact earlier application artifacts, and restored `0.3.0` again. Each apply updated two Lambda packages and five existing frontend objects. All 13 served frontend hashes and both Lambda package hashes matched their expected versions; the fleet hash and revision 16 stayed unchanged. See the [rehearsal report](../evidence/release-rehearsal.json).

Build #7 stopped before AWS during local tests with Windows socket error 10055. All 11 server tests then passed unchanged in the same Jenkins context, and build #8 succeeded in 177.5 seconds with 105 tests and all seven stage reports passing. No definitive cause is claimed for the earlier socket failure. Temporary authentication-test users were removed.

Rollback used verified source snapshots and Terraform redeployment. It did not restore or revert DynamoDB data. The rehearsal-only fleet baseline is archived; ordinary demo actions can now advance the fleet state normally.

## Local start, stop, and recover

Run `start.cmd` on Windows or `python3 -m backend.server` from the project directory. Visit `http://127.0.0.1:8765`. Keep the terminal open. Ctrl+C stops the server without deleting stored state.

The app stores state in `data/edgeops.sqlite3`. The standalone agent stores buffered telemetry in `data/device-agent.sqlite3`. These contain synthetic demonstration data and are excluded from the distribution ZIP. Do not delete them while a process is using them.

If port 8765 is busy, run `scripts/start.ps1 -Port 8766` and open `http://127.0.0.1:8766`. Pass the same URL to the standalone agent's `--url` argument.

## Explain the recovery demo

1. Start with all three devices healthy and simulation paused.
2. Record the accepted-reading and duplicate counters.
3. Disconnect one device. Its offline incident opens immediately because this is an operator-driven simulator.
4. Generate several simulation ticks. Other devices continue delivering while the disconnected device accumulates buffered readings.
5. Reconnect. The backend drains its simulated outbox and resolves the offline incident.
6. Replay the last event. The duplicate count increases; accepted telemetry does not.
7. Export diagnostic JSON and describe the timeline.

The dashboard's one-click recovery demo automates this sequence. The separate `device_agent.py` process proves an actual disk-backed outbox across process restarts and network failure.

## Investigate an overheating incident

Select a device and choose its heat action. A synthetic reading above the shared 55 C demonstration threshold opens an incident. Inspect the chart and incident timeline, acknowledge if desired, and then cool the device. The incident retains its resolution timestamp.

## Troubleshooting

| Symptom | Check |
|---|---|
| Browser cannot connect | Ensure the server terminal remains open and the port matches the URL. |
| UI shows an API failure | The UI preserves the last known state and displays an error. Check terminal logs, then retry. |
| Data stops changing | Start simulation; it is paused by default. A disconnected device buffers instead of updating current readings. |
| Duplicate/stale counter rises | A repeated event ID or sequence at/below the device's high-water mark was deliberately suppressed. |
| Buffer is full | Reconnect the simulated device. Sampling is paused at the bound rather than silently dropping generated readings. |
| Agent fails to send | Readings remain in the agent's SQLite outbox. Restore connectivity and use `--flush-only`. |
| Local API returns403 | Access using localhost or127.0.0.1. Cross-origin writes and non-loopback hostnames are rejected. |

## Backup and restore exercise

For a simple consistent backup, stop the server first and copy `data/edgeops.sqlite3` to another filename. Restart and make a visible change. Stop the server again, preserve the changed file, restore the backup under the original name, and restart. Verify the previous state appears. SQLite WAL files can be active while the process is running, so copying the main file from a running server is not the documented backup procedure.

## Local HTTP interface

| Method | Path | Meaning |
|---|---|---|
| GET | `/api/health` | Local health, persistence mode, demo marker |
| GET | `/api/state` | Public fleet snapshot |
| POST | `/api/tick` | Generate readings; body `{"steps":1}` |
| POST | `/api/actions` | Body includes `deviceId` and `action` |
| POST | `/api/telemetry` | Ingest up to100 validated events |
| GET | `/api/export` | Download diagnostic JSON |
| POST | `/api/reset` | Reset synthetic data |

Available device actions: `disconnect`, `reconnect`, `heat`, `cool`, `replay`, and `acknowledge`. Telemetry fields: `eventId`, `deviceId`, integer `sequence`, UTC `at`, `temperature`, `battery`, and `signal`. Battery and signal are percentages. The entire batch is validated before any local mutation. Maximum HTTP body size is64KiB.
