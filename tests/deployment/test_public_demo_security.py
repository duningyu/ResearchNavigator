import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCANNER = PROJECT_ROOT / "scripts" / "deployment" / "scan_public_demo_artifacts.py"


def test_vercel_headers_bound_browser_capabilities_and_tunnel_connections() -> None:
    config = json.loads((PROJECT_ROOT / "vercel.json").read_text(encoding="utf-8"))
    headers = {item["key"]: item["value"] for item in config["headers"][0]["headers"]}
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in headers["Permissions-Policy"]
    assert "microphone=()" in headers["Permissions-Policy"]
    csp = headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "connect-src 'self' https://*.trycloudflare.com" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp


def run_scanner(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCANNER), "--root", str(root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_bundle_scanner_passes_safe_content_and_fails_secrets_or_local_paths(
    tmp_path: Path,
) -> None:
    (tmp_path / "safe.js").write_text("const endpoint = 'https://example.test';", encoding="utf-8")
    safe = run_scanner(tmp_path)
    assert safe.returncode == 0, safe.stdout + safe.stderr
    assert json.loads(safe.stdout)["status"] == "PASS"

    (tmp_path / "leak.js").write_text(
        "const LLM_API_KEY = 'not-a-real-key'; const path = 'E:\\\\private\\\\data';",
        encoding="utf-8",
    )
    leaked = run_scanner(tmp_path)
    assert leaked.returncode != 0
    payload = json.loads(leaked.stdout)
    assert payload["status"] == "FAIL"
    assert {finding["kind"] for finding in payload["findings"]} == {
        "FORBIDDEN_SECRET_NAME",
        "WINDOWS_ABSOLUTE_PATH",
    }
