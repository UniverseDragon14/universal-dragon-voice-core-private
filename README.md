# Novakutty Intent-to-Proof Console

Private browser console and Python backend that convert a small natural-language request set into bounded QBIT NOVA C demonstrations and evidence receipts.

## Implemented flow

~~~text
Browser request
  -> fixed intent classifier
  -> STATUS | GHZ | APPROVAL_DEMO | REJECTION_DEMO
  -> allowlisted command or admission check
  -> structured result
  -> JSON receipt + SHA-256 evidence digest
~~~

### Front end

**index.html** provides:

- browser speech recognition when supported;
- typed request input;
- proof-pipeline state display;
- NOVA/EVE explanations;
- verified markers and technical output;
- fixed demo presets;
- receipt and digest display.

It calls **/api/health** and **/api/intent**.

### Backend

**intent_server.py**:

- binds to **127.0.0.1** by default;
- accepts a maximum 8 KiB request and 500-character message;
- permits one execution at a time;
- uses fixed command arrays with no shell=True;
- applies execution timeouts and output limits;
- supports only status, bounded 3-qbit GHZ, safe-admission, and rejection demonstrations;
- stores private-mode receipts under **receipts/**.

## Run locally

The backend expects a QBIT NOVA C repository containing the referenced proof/admission scripts.

~~~bash
export NOVAKUTTY_REPO="$HOME/qbit-nova-c"
python3 intent_server.py
~~~

Then open:

~~~text
http://127.0.0.1:8102/
~~~

Use **NOVAKUTTY_PORT** only when a different loopback port is required.

## Truth boundary

- Runtime: software virtual QCPU on classical hardware.
- Physical QPU: not present or claimed.
- Speech recognition: browser feature, not a custom STT model.
- Evidence digest: SHA-256 integrity digest, not a digital signature.
- Unknown requests: rejected without execution.
- This is not a general terminal, unrestricted voice controller, or live hardware-control service.

Generated logs, PID files, receipts, and historical HTML backups are evidence/runtime artifacts, not source modules.

## Security

Keep the service on loopback. Do not place it behind a public tunnel without authentication, rate limits, origin controls, and a fresh threat review.
