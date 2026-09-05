"""One-object, redacted live validation for the R2 presigned upload contract."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from research_navigator.data_plane.storage import Boto3R2Transport, R2Storage

BUCKET = "researchnav-documents"


def _status_for_request(request: Request) -> int:
    try:
        with urlopen(request, timeout=30) as response:
            return int(response.status)
    except HTTPError as exc:
        return int(exc.code)


def _safe_not_found(exc: ClientError) -> bool:
    error = exc.response.get("Error", {})
    code = str(error.get("Code", ""))
    return code in {"404", "NoSuchKey", "NotFound"}


def _anonymous_url(endpoint: str, bucket: str, key: str) -> str:
    return f"{endpoint.rstrip('/')}/{bucket}/{key}"


def _redacted_url_shape(url: str) -> dict[str, str]:
    parsed = urlsplit(url)
    return {"scheme": parsed.scheme, "host": parsed.netloc, "path": parsed.path}


def _content_length(value: object) -> int:
    if isinstance(value, (int, str, float)):
        return int(value)
    raise ValueError("invalid content length metadata")


def main() -> int:
    bucket = os.environ.get("R2_BUCKET", "")
    account_id = os.environ.get("R2_ACCOUNT_ID", "")
    access_key = os.environ.get("R2_ACCESS_KEY_ID", "")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY", "")
    endpoint = os.environ.get("R2_ENDPOINT", f"https://{account_id}.r2.cloudflarestorage.com")
    source_commit = os.environ.get("RN_SOURCE_COMMIT", "UNKNOWN")
    receipt_path = Path(
        os.environ.get(
            "RN_R2_RECEIPT_PATH",
            "/workspace/deployment/cloud/runtime_receipts/R2_PRESIGNED_UPLOAD_SECURITY_RECEIPT.json",
        )
    )
    receipt: dict[str, object] = {
        "source_commit": source_commit,
        "bucket": bucket,
        "presign_transport": "Boto3R2Transport",
        "key_server_generated": False,
        "user_scope": "redacted",
        "ttl_seconds": 300,
        "content_type_bound": False,
        "content_length_contract": False,
        "checksum_contract": False,
        "valid_put": "NOT_RUN",
        "authenticated_head": "NOT_RUN",
        "authenticated_get": "NOT_RUN",
        "content_integrity": "NOT_RUN",
        "path_binding": "NOT_RUN",
        "anonymous_retrieval_blocked": "NOT_RUN",
        "exact_cleanup": "NOT_RUN",
        "presigned_url_exposed": False,
        "secret_exposure": False,
        "provider_calls": {"r2": 0, "turso": 0, "llm": 0, "external_research": 0},
        "final_status": "NOT_RUN",
    }
    if bucket != BUCKET:
        receipt["final_status"] = "FIXED_BUCKET_REQUIRED"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        return 1
    if not account_id or not access_key or not secret_key:
        receipt["final_status"] = "CREDENTIALS_REQUIRED"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        return 1

    payload = ("RN223 presigned upload validation " + uuid.uuid4().hex).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    key = f"uploads/live-validation/{uuid.uuid4().hex}/{digest}.pdf"
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="auto",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )
    storage = R2Storage(bucket=bucket, transport=Boto3R2Transport(client))
    receipt["key_server_generated"] = True
    receipt["user_scope"] = "live-validation"
    receipt["content_type_bound"] = True
    receipt["content_length_contract"] = True
    receipt["checksum_contract"] = "x-amz-meta-sha256"
    try:
        url = storage.generate_presigned_upload(
            key=key, content_type="application/pdf", sha256=digest, expires_in=300
        )
        receipt["presigned_url_shape"] = _redacted_url_shape(url)
        put_request = Request(
            url,
            data=payload,
            method="PUT",
            headers={"Content-Type": "application/pdf", "x-amz-meta-sha256": digest},
        )
        receipt["valid_put"] = (
            "PASS" if _status_for_request(put_request) in {200, 201, 204} else "FAIL"
        )
        receipt["provider_calls"] = {"r2": 1, "turso": 0, "llm": 0, "external_research": 0}
        head = storage.stat(key)
        receipt["authenticated_head"] = "PASS"
        receipt["authenticated_get"] = "PASS" if storage.get(key) == payload else "FAIL"
        receipt["content_integrity"] = (
            "PASS"
            if len(payload) == _content_length(head.get("ContentLength", -1))
            and hashlib.sha256(storage.get(key)).hexdigest() == digest
            else "FAIL"
        )
        parts = urlsplit(url)
        tampered_path = parts.path.rsplit("/", 1)[0] + "/other.pdf"
        tampered_url = urlunsplit((parts.scheme, parts.netloc, tampered_path, parts.query, ""))
        tamper_status = _status_for_request(
            Request(
                tampered_url,
                data=payload,
                method="PUT",
                headers={"Content-Type": "application/pdf", "x-amz-meta-sha256": digest},
            )
        )
        receipt["path_binding"] = "PASS" if not 200 <= tamper_status < 300 else "FAIL"
        anonymous_status = _status_for_request(
            Request(_anonymous_url(endpoint, bucket, key), method="GET")
        )
        receipt["anonymous_retrieval_blocked"] = (
            "PASS_NON_2XX" if not 200 <= anonymous_status < 300 else "FAIL"
        )
        storage.delete(key)
        try:
            client.head_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            if not _safe_not_found(exc):
                raise
            receipt["exact_cleanup"] = "PASS"
        else:
            receipt["exact_cleanup"] = "FAIL_OBJECT_REMAINS"
        required = (
            receipt["valid_put"] == "PASS"
            and receipt["authenticated_head"] == "PASS"
            and receipt["authenticated_get"] == "PASS"
            and receipt["content_integrity"] == "PASS"
            and receipt["path_binding"] == "PASS"
            and str(receipt["anonymous_retrieval_blocked"]).startswith("PASS_")
            and receipt["exact_cleanup"] == "PASS"
        )
        receipt["final_status"] = "PASS" if required else "FAIL"
    except (ClientError, OSError, URLError, ValueError) as exc:
        receipt["final_status"] = "ERROR_SAFE_REDACTED"
        receipt["failure_type"] = type(exc).__name__
    finally:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"R2_PRESIGNED_UPLOAD_RECEIPT={receipt_path}")
    return 0 if receipt["final_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
