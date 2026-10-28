# Local demo, checks and CI

Moved from the README on 2026-10-25. Everything here runs without an AWS account.

## Run now

On this Windows computer, double-click **start.cmd**, then open `http://127.0.0.1:8765`. Keep the terminal running. Ctrl+C stops the app; data survives a restart.

The launcher discovers Python 3.11+ (on PATH, or a bundled runtime the launcher knows about). No pip install, npm install, API key, or cloud account is required.

Other systems with Python 3.11+:

```sh
python3 -m backend.server --port 8765 --data data/edgeops.sqlite3
```

The dashboard starts with seeded synthetic readings and simulation paused. Use **Start simulation** to generate new readings. You can inspect the same stored fleet through Overview, Devices, Incidents, and Activity.

## A two-minute demonstration

1. Click **Run recovery demo** to disconnect a simulated device, generate buffered readings, reconnect, and test duplicate suppression.
2. Select a device and trigger **Heat**. Inspect its incident, then **Cool** it and verify recovery.
3. Click **Export diagnostics** to inspect the current state, event history, and incident evidence as JSON, then use the download or selection option.
4. Restart the server and show that the fleet state persists. **Reset demo data** starts a clean synthetic fleet when desired.

Guided simulation uses a server-side model of a device outbox. To demonstrate a genuinely separate, persistent edge process, use the command-line agent below.

## Real offline outbox

Pause dashboard simulation while demonstrating the standalone agent. From the project directory, use your Python executable:

```sh
python scripts/device_agent.py --offline --count 5
python scripts/device_agent.py --flush-only
python scripts/device_agent.py --replay-last
```

The first command writes five readings to `data/device-agent.sqlite3` without making any network request. The second sends them to the local HTTP API and removes only acknowledged batches. The third sends the same event ID again so you can show the duplicate counter increase without another accepted reading.

Stop the server before attempting delivery to demonstrate a network failure; the outbox remains intact. Restart the server and run `--flush-only`. You can also pass `--temperature 70`, `--device edge-001`, `--count 10`, and `--url http://127.0.0.1:8765`.

On Windows without Python on PATH:

```powershell
. .\scripts\runtime.ps1
$edgePython = Get-EdgeOpsPython
& $edgePython scripts/device_agent.py --offline --count 5
& $edgePython scripts/device_agent.py --flush-only
& $edgePython scripts/device_agent.py --replay-last
```


## Checks and DevOps files

Windows:

```powershell
.\scripts\check.ps1
```

Other systems:

```sh
python3 -m unittest discover -s tests -v
node --test frontend/tests/*.test.mjs
python3 -m unittest discover -s infra/tests -v
```

Node.js 20+ is needed only for frontend tests. The application itself runs without Node.

The authenticated local Jenkins controller is available at `http://127.0.0.1:8080` (local to the owner's machine) while its manual process is running. Open the `edgeops-deploy` job and use **Build with Parameters**. Leave **DEPLOY_AWS** unchecked for tests, Docker health, Terraform plan review, and cloud checks; selecting it permits only reviewed code updates to existing Lambda functions and frontend objects. Resource creation/deletion and permission changes are rejected. Builds #5, #6 and #8 each applied seven updates successfully, verified the deployed artifacts, and removed their temporary authentication-test users without changing fleet data. This rollback redeploys verified source snapshots; it does not roll back the database or switch Lambda aliases.

See [CI pipeline operation](../reference/ci-pipeline.md) for stages, private state, restart requirements, and limitations. This Windows setup uses the existing local workspace and private credential wrappers; it does not require GitHub or another AWS server and is not a standalone Jenkins distribution.

`Dockerfile` provides a non-root container option; a Docker daemon is needed to build and run it:

```sh
docker build -t edgeops:local .
docker run --rm -p 127.0.0.1:8765:8765 -v edgeops-data:/data edgeops:local
```
