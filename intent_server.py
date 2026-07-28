#!/usr/bin/env python3
"""
Novakutty Intent-to-Proof Backend

Security boundaries:
- Fixed allowlist only
- No shell=True
- No arbitrary command execution
- One workload at a time
- Bounded request size and execution timeout
- Software Virtual QCPU on classical hardware
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import uuid

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parent
REPO_DIR = Path(
    os.environ.get(
        "NOVAKUTTY_REPO",
        str(Path.home() / "qbit-nova-c"),
    )
).resolve()

HOST = "127.0.0.1"
PORT = int(os.environ.get("NOVAKUTTY_PORT", "8102"))

MAX_REQUEST_BYTES = 8_192
MAX_MESSAGE_LENGTH = 500
MAX_OUTPUT_LENGTH = 12_000

EXECUTION_LOCK = threading.Lock()

SAFE_ENV = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "HOME": str(Path.home()),
    "LANG": "C",
    "LC_ALL": "C",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def send_json(handler: BaseHTTPRequestHandler, status: int, data: dict[str, Any]) -> None:
    payload = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("X-Frame-Options", "DENY")
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.end_headers()
    handler.wfile.write(payload)


def run_fixed_command(
    command: list[str],
    timeout: int = 45,
) -> tuple[int, str]:
    completed = subprocess.run(
        command,
        cwd=REPO_DIR,
        env=SAFE_ENV,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )

    output = "\n".join(
        part.strip()
        for part in (completed.stdout, completed.stderr)
        if part.strip()
    )

    if len(output) > MAX_OUTPUT_LENGTH:
        output = output[-MAX_OUTPUT_LENGTH:]

    return completed.returncode, output


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}

    if not path.is_file():
        return values

    for raw_line in path.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)

        if key.replace("_", "").isalnum():
            values[key.strip()] = value.strip()

    return values


def classify_intent(message: str) -> str:
    text = message.casefold()

    rejection_terms = (
        "unbounded",
        "unlimited",
        "heavy workload",
        "unsafe",
        "bypass",
        "disable guard",
        "ignore approval",
        "dangerous",
        "over limit",
        "maximum workload",
        "root action",
        "kernel module",
        "device node",
    )

    ghz_terms = (
        "ghz",
        "3-qbit",
        "3 qubit",
        "three qbit",
        "three qubit",
        "quantum proof",
    )

    approval_terms = (
        "approval",
        "safe workload",
        "standard workload",
        "bounded workload",
        "admission",
        "approve request",
    )

    status_terms = (
        "status",
        "health",
        "system ready",
        "runtime state",
        "repository state",
        "version",
    )

    if any(term in text for term in rejection_terms):
        return "REJECTION_DEMO"

    if any(term in text for term in ghz_terms):
        return "GHZ"

    if any(term in text for term in approval_terms):
        return "APPROVAL_DEMO"

    if any(term in text for term in status_terms):
        return "STATUS"

    return "UNKNOWN"


def create_receipt(result: dict[str, Any]) -> tuple[str, str]:
    receipt_dir = APP_DIR / "receipts"
    receipt_dir.mkdir(mode=0o700, exist_ok=True)

    receipt_body = {
        "schema": "novakutty.intent-proof.receipt.v1",
        "generated_utc": utc_now(),
        "creator_owner": "UNIVERSAL_DRAGON_ASLAM",
        "product": "NOVAKUTTY",
        "core": "QBIT_NOVA_C",
        "truth_boundary": {
            "runtime": "SOFTWARE_VIRTUAL_QCPU",
            "host": "CLASSICAL_CPU",
            "physical_qpu_present": False,
            "arbitrary_shell": "DENY",
            "root_action": "DENY",
            "kernel_module": "DENY",
            "device_node_creation": "DENY",
        },
        "result": result,
    }

    canonical = json.dumps(
        receipt_body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    digest = hashlib.sha256(canonical).hexdigest()

    receipt_body["evidence_digest"] = {
        "algorithm": "SHA-256",
        "value": digest,
        "note": "Evidence digest only; not a digital signature.",
    }

    receipt_name = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
        + ".json"
    )

    receipt_path = receipt_dir / receipt_name
    receipt_path.write_text(
        json.dumps(
            receipt_body,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    receipt_path.chmod(0o600)

    return f"receipts/{receipt_name}", digest


def execute_status() -> dict[str, Any]:
    head_code, head_output = run_fixed_command(
        ["git", "rev-parse", "--short", "HEAD"],
        timeout=10,
    )

    tree_code, tree_output = run_fixed_command(
        ["git", "status", "--porcelain"],
        timeout=10,
    )

    clean = tree_code == 0 and not tree_output.strip()
    ready = head_code == 0 and tree_code == 0

    return {
        "intent": "STATUS",
        "decision": "APPROVED",
        "executed": True,
        "status": "PASS" if ready else "FAIL",
        "reason": "Read-only repository and runtime status inspection.",
        "markers": [
            f"GIT_HEAD={head_output.strip() or 'UNKNOWN'}",
            f"WORKING_TREE={'CLEAN' if clean else 'CHANGED'}",
            "BOUNDARY=SOFTWARE_VIRTUAL_QCPU",
            "PHYSICAL_QPU_PRESENT=NO",
        ],
        "runtime_output": (
            f"GIT_HEAD={head_output.strip() or 'UNKNOWN'}\n"
            f"WORKING_TREE={'CLEAN' if clean else 'CHANGED'}"
        ),
        "explanation": (
            "NOVA performed a read-only status check. "
            "No workload, root action, kernel operation, or device-node action was used."
        ),
    }


def execute_ghz() -> dict[str, Any]:
    code, output = run_fixed_command(
        ["bash", "scripts/proof_ghz.sh", "3", "20"],
        timeout=60,
    )

    passed = (
        code == 0
        and (
            "PASS: QCPU_GHZ_PROOF_READY" in output
            or "GHZ PROOF PASSED" in output
        )
    )

    return {
        "intent": "GHZ",
        "decision": "APPROVED",
        "executed": True,
        "status": "PASS" if passed else "FAIL",
        "reason": (
            "Bounded allowlisted 3-qbit GHZ proof with 20 runs."
        ),
        "markers": [
            "QUBITS=3",
            "RUNS=20",
            f"GHZ={'PASS' if passed else 'FAIL'}",
            "BOUNDARY=SOFTWARE_VIRTUAL_QCPU",
        ],
        "runtime_output": output,
        "explanation": (
            "NOVA approved a bounded GHZ proof. "
            "QBIT NOVA C executed the proof on a classical CPU and checked "
            "that only valid GHZ-correlated outcomes were produced."
        ),
    }


def execute_admission(intent: str) -> dict[str, Any]:
    code, output = run_fixed_command(
        ["bash", "scripts/qcpu_workload_admission.sh"],
        timeout=45,
    )

    values = parse_env_file(
        REPO_DIR / ".qcpu" / "workload_admission.env"
    )

    standard_admission = values.get(
        "QCPU_STANDARD_ADMISSION",
        "UNKNOWN",
    )

    heavy_admission = values.get(
        "QCPU_HEAVY_ADMISSION",
        "UNKNOWN",
    )

    policy_pass = (
        code == 0
        and values.get("QCPU_ADMISSION_CONTROLLER_STATUS")
        == "PASS: WORKLOAD_ADMISSION_POLICY_ENFORCED"
    )

    if intent == "APPROVAL_DEMO":
        approved = standard_admission == "ADMIT_WORKLOAD"

        return {
            "intent": intent,
            "decision": "APPROVED" if approved else "REJECTED",
            "executed": False,
            "status": "PASS" if approved and policy_pass else "FAIL",
            "reason": (
                "The bounded standard workload satisfied the admission policy. "
                "This demo performs admission only; it does not execute the workload."
            ),
            "markers": [
                f"STANDARD_ADMISSION={standard_admission}",
                f"POLICY={'PASS' if policy_pass else 'FAIL'}",
                "OWNER_APPROVAL=REQUIRED",
                "ARBITRARY_SHELL=DENY",
            ],
            "runtime_output": output,
            "explanation": (
                "NOVA evaluated the request against fixed workload limits. "
                "The standard workload was admitted, but execution remains a separate controlled step."
            ),
        }

    rejected = heavy_admission == "REJECT_WORKLOAD"

    return {
        "intent": intent,
        "decision": "REJECTED" if rejected else "APPROVED_UNEXPECTEDLY",
        "executed": False,
        "status": "PASS" if rejected and policy_pass else "FAIL",
        "reason": (
            "The heavy or unbounded workload exceeded the approved admission boundary."
        ),
        "markers": [
            f"HEAVY_ADMISSION={heavy_admission}",
            f"POLICY={'PASS' if policy_pass else 'FAIL'}",
            "DANGEROUS_ACTION=DENY",
            "EXECUTED=NO",
        ],
        "runtime_output": output,
        "explanation": (
            "NOVA rejected the unsafe workload before execution. "
            "QBIT NOVA C was not started for this request, and an evidence receipt was still produced."
        ),
    }


def execute_unknown(message: str) -> dict[str, Any]:
    return {
        "intent": "UNKNOWN",
        "decision": "REJECTED",
        "executed": False,
        "status": "PASS",
        "reason": (
            "The request did not match the fixed Novakutty allowlist."
        ),
        "markers": [
            "ALLOWLIST=STATUS,GHZ,APPROVAL_DEMO,REJECTION_DEMO",
            "ARBITRARY_SHELL=DENY",
            "EXECUTED=NO",
        ],
        "runtime_output": "",
        "explanation": (
            "NOVA could not map the request to an approved operation. "
            "Nothing was executed. Use status, GHZ, safe approval, or unsafe rejection demonstrations."
        ),
        "received_request": message[:120],
    }


def process_intent(message: str) -> dict[str, Any]:
    intent = classify_intent(message)

    if intent == "STATUS":
        result = execute_status()
    elif intent == "GHZ":
        result = execute_ghz()
    elif intent in {"APPROVAL_DEMO", "REJECTION_DEMO"}:
        result = execute_admission(intent)
    else:
        result = execute_unknown(message)

    receipt_path, digest = create_receipt(result)

    result["receipt"] = {
        "path": receipt_path,
        "sha256": digest,
        "digest_type": "EVIDENCE_DIGEST_NOT_DIGITAL_SIGNATURE",
    }

    return result


class NovakuttyHandler(BaseHTTPRequestHandler):
    server_version = "NovakuttyIntentProof/1.0"

    def log_message(self, format_string: str, *args: Any) -> None:
        print(
            f"{self.address_string()} "
            f"[{utc_now()}] "
            f"{format_string % args}",
            flush=True,
        )

    def do_HEAD(self) -> None:
        if self.path in {"/", "/index.html"}:
            index_path = APP_DIR / "index.html"

            if not index_path.is_file():
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            size = index_path.stat().st_size

            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/html; charset=utf-8",
            )
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            return

        if self.path == "/api/health":
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8",
            )
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            return

        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path in {"/", "/index.html"}:
            index_path = APP_DIR / "index.html"

            if not index_path.is_file():
                send_json(
                    self,
                    404,
                    {"ok": False, "error": "index.html not found"},
                )
                return

            payload = index_path.read_bytes()

            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/html; charset=utf-8",
            )
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(payload)
            return

        if self.path == "/api/health":
            send_json(
                self,
                200,
                {
                    "ok": True,
                    "product": "NOVAKUTTY",
                    "service": "INTENT_TO_PROOF",
                    "allowlist": [
                        "STATUS",
                        "GHZ",
                        "APPROVAL_DEMO",
                        "REJECTION_DEMO",
                    ],
                    "repo_available": REPO_DIR.is_dir(),
                    "truth_boundary": "SOFTWARE_VIRTUAL_QCPU",
                    "physical_qpu_present": False,
                    "utc": utc_now(),
                },
            )
            return

        if self.path.startswith("/receipts/"):
            receipt_name = self.path.removeprefix("/receipts/")

            if (
                not receipt_name.endswith(".json")
                or "/" in receipt_name
                or "\\" in receipt_name
                or ".." in receipt_name
            ):
                send_json(
                    self,
                    400,
                    {"ok": False, "error": "Invalid receipt path"},
                )
                return

            receipt_path = APP_DIR / "receipts" / receipt_name

            if not receipt_path.is_file():
                send_json(
                    self,
                    404,
                    {"ok": False, "error": "Receipt not found"},
                )
                return

            payload = receipt_path.read_bytes()

            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8",
            )
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)
            return

        send_json(
            self,
            404,
            {"ok": False, "error": "Route not found"},
        )

    def do_POST(self) -> None:
        if self.path != "/api/intent":
            send_json(
                self,
                404,
                {"ok": False, "error": "Route not found"},
            )
            return

        content_type = self.headers.get("Content-Type", "")

        if "application/json" not in content_type:
            send_json(
                self,
                415,
                {
                    "ok": False,
                    "error": "Content-Type must be application/json",
                },
            )
            return

        try:
            content_length = int(
                self.headers.get("Content-Length", "0")
            )
        except ValueError:
            content_length = 0

        if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
            send_json(
                self,
                413,
                {"ok": False, "error": "Invalid request size"},
            )
            return

        try:
            body = self.rfile.read(content_length)
            request_data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            send_json(
                self,
                400,
                {"ok": False, "error": "Invalid JSON body"},
            )
            return

        message = request_data.get("message")

        if not isinstance(message, str):
            send_json(
                self,
                400,
                {"ok": False, "error": "message must be a string"},
            )
            return

        message = " ".join(message.split())

        if not message or len(message) > MAX_MESSAGE_LENGTH:
            send_json(
                self,
                400,
                {
                    "ok": False,
                    "error": "message must contain 1 to 500 characters",
                },
            )
            return

        if not EXECUTION_LOCK.acquire(blocking=False):
            send_json(
                self,
                409,
                {
                    "ok": False,
                    "error": "Another bounded workload is currently running",
                },
            )
            return

        try:
            result = process_intent(message)

            send_json(
                self,
                200,
                {
                    "ok": True,
                    "request": message,
                    **result,
                },
            )
        except subprocess.TimeoutExpired:
            send_json(
                self,
                504,
                {
                    "ok": False,
                    "decision": "REJECTED",
                    "executed": False,
                    "error": "Bounded execution timeout reached",
                },
            )
        except Exception as error:
            print(
                f"SERVER_ERROR={type(error).__name__}: {error}",
                flush=True,
            )

            send_json(
                self,
                500,
                {
                    "ok": False,
                    "decision": "REJECTED",
                    "executed": False,
                    "error": "Intent-to-Proof processing failed safely",
                },
            )
        finally:
            EXECUTION_LOCK.release()


def main() -> None:
    if not REPO_DIR.is_dir():
        raise SystemExit(
            f"QBIT NOVA C repository not found: {REPO_DIR}"
        )

    server = ThreadingHTTPServer(
        (HOST, PORT),
        NovakuttyHandler,
    )

    print("============================================================")
    print("NOVAKUTTY INTENT-TO-PROOF SERVER")
    print("============================================================")
    print(f"HOST={HOST}")
    print(f"PORT={PORT}")
    print(f"REPO={REPO_DIR}")
    print("ALLOWLIST=STATUS,GHZ,APPROVAL_DEMO,REJECTION_DEMO")
    print("ARBITRARY_SHELL=DENY")
    print("PHYSICAL_QPU_PRESENT=NO")
    print("READY=http://127.0.0.1:%d" % PORT)
    print(flush=True)

    server.serve_forever()


if __name__ == "__main__":
    main()
