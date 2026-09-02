# RN223 Offline Parity Harness Closure

## Objective

Close the offline Linux parity evidence boundary without making live Turso/R2 calls or prompting for secrets. Keep the Frozen Core unchanged and preserve the distinction between provider doubles and live-provider evidence.

## Steps

1. **Executable source provenance**
   - Verify repository root, branch, HEAD, context guard, and relevant source paths.
   - Pass the host source commit explicitly into the container; do not rely on container Git metadata.
   - Produce a secret-free provenance receipt and audit only executable files participating in the harness.

2. **Reusable Linux parity image/runtime**
   - Add a pinned Python 3.12 Linux image definition using the authoritative `pyproject.toml`/`uv.lock` dependency contract.
   - Build or reuse one deterministic image and validate Python, `sqlalchemy-libsql`, dialect loading, worker imports, and parity-runner imports.
   - Run the harness with `docker run --rm --network none` and only the verified worktree mounted at `/workspace`.

3. **Offline deterministic provider doubles**
   - Add explicit dependency-injection seams for database and storage composition, retaining existing production defaults.
   - Implement deterministic, filesystem-backed offline Turso and R2 doubles behind the existing data-plane interfaces.
   - Ensure the offline path cannot construct boto3/R2 or Turso network clients and accepts no credentials.

4. **Full offline `evidence_workflow_v1` parity**
   - Use the actual application composition, ingestion path, job creation, worker claim, and `execute_job` workflow.
   - Persist inputs/metadata and workflow outputs through the offline provider doubles, not normal local-storage mode.
   - Exercise the frozen PUBLIC_CORE path and validate terminal durable state, object identity, and content integrity.

5. **Fresh-process reload and cleanup**
   - Destroy the temporary application workspace after the first process.
   - Start a second fresh Python process with only logical IDs and the offline provider directory.
   - Reload from the offline Turso/R2 doubles, verify integrity, then delete only the exact validation objects.

6. **Receipt and error/exit-code contracts**
   - Emit `OFFLINE_PARITY_HARNESS_RECEIPT.json` plus per-run receipts with no secrets or credential-bearing data.
   - Record `runtime_mode=OFFLINE_PROVIDER_DOUBLE` and `cloud_parity_claim=NOT_A_LIVE_PROVIDER_CLAIM`.
   - Enforce PASS -> exit 0 and ERROR -> nonzero, with safe stage/error telemetry.
   - Execute three fresh runs with unique execution IDs and aggregate only safe status metadata.

7. **Source-clean verification**
   - Run fresh tests, compile checks, PowerShell syntax checks, context guard, secret scans, and `git diff --check`.
   - Explicitly stage only verified source/tests/configuration; preserve unrelated existing evidence artifacts.
   - Commit the verified harness and require the participating executable source set to be clean afterward.

8. **Final live-parity preflight**
   - Run a no-secret preflight after all three offline runs and verify the offline receipts, image/runtime, provenance, and source-clean gates.
   - Update the master status without claiming live Turso/R2 parity.
   - Stop at `WAITING_USER_LINUX_PARITY_SECRET_ENTRY_LOCAL`; provide the exact approved live command only after offline closure.

## Acceptance

- Three independent offline Docker runs pass with `--network none`.
- Fresh-process reload, temporary-workspace destruction, durable state, and content integrity pass.
- No provider calls, prompts, secrets, untracked participating executable source, or Frozen Core changes.
- All required fresh verification checks pass and the final live command is not executed automatically.
