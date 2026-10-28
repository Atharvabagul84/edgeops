# Deliberate MVP limits

Moved from the README on 2026-10-25.


- Single local operator, three predefined synthetic devices, and no local login. The server binds to loopback by default. Do not expose the local HTTP server to a public network.
- Local telemetry processing is synchronous. The displayed local counters do not claim that AWS SQS or CloudWatch is connected.
- Disconnect incidents are driven by simulator commands, not automatic detection of a physical device's missing heartbeat. Temperature incidents use a demo threshold of 55 C for all three devices.
- Recent history is bounded. Older or out-of-order sequence numbers are ignored rather than archived; this protects current state but is not a lossless telemetry archive.
- The dashboard simulator buffers at most 100 readings per device and pauses sampling when full. The standalone agent buffers up to 10,000 readings.
- No multi-tenancy, firmware rollout, anomaly ML, remote shell, commercial billing, or production uptime claim.
- AWS resources, core API/queue flows and the authenticated browser demonstration are verified. Remaining forced-DLQ, token-expiry and operational checks are tracked in the validation report. Cloud operators share one demo fleet; this is not tenant isolation. The MVP sign-in flow does not implement MFA challenges.

All initial fleet names, readings, incidents, and firmware labels are demonstration data.
