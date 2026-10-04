# Quickstart: Validate Read-only Drift and Compliance Detection

This guide records the post-approval validation path. Separate implementation approval was received
on 2026-09-22, and canonical validation completed on 2026-09-23.

## Prerequisites

- Existing Features 001-004 and 006 runtime prerequisites are satisfied.
- Canonical Nautobot 3.2.5 intent is available.
- A supported real SR Linux device is reachable through the existing device-access overlay.
- The API has device credentials only in server-side runtime settings.
- Acceptance uses existing state; do not edit Nautobot or device configuration to manufacture drift.

## Automated Validation

Run the focused pure comparison and API tests:

```bash
uv run pytest tests/unit/test_device_comparison.py tests/unit/test_api_devices.py
```

Run the complete Python regression suite:

```bash
uv run pytest
```

Run frontend tests and production build:

```bash
npm --prefix ui test -- --run
npm --prefix ui run build
```

Expected evidence:

- Matching configuration is in sync.
- Every supported expected mismatch is isolated to its configuration check.
- Interface/BGP operational failures do not become drift.
- Expected address presence and readiness split according to `contracts/comparison.md`.
- Source failures produce unavailable observations without raw payloads.
- Successful `live=true` performs exactly one device read; `live=false` and intent failure perform
  zero; no success or failure path automatically retries the device.
- Malformed leaf types make both observations unavailable rather than becoming drift or health.
- Unexpected observed mapping keys create no checks and do not alter aggregate status.
- Existing Feature 001-006 tests remain passing.

## Read-only Canonical Acceptance

Start the already-defined UI/API profile and device-access overlay using the existing Feature 006
commands. Open one canonical device detail route and permit its single on-demand live read.

Verify against source observations without changing either source:

1. Nautobot intended hostname, interfaces/prefixes, local ASN, and neighbors match the Intended State section.
2. Configuration Drift and Operational Health show separate statuses and checks.
3. Both current results have the same observation time and device source context.
4. A currently down BGP session, if naturally present, affects only Operational Health.
5. Later scheduled page refreshes cause no additional device read.
6. Historical Validation remains separately labeled and is not presented as current drift.
7. Browser/API/log inspection reveals no raw config, response payload, credential, or mutation control.
8. Each current section shows separate Nautobot-intent and device-read availability.
9. Desktop and 375-pixel views have no horizontal page overflow and retain status text/non-color cues.

If canonical state has no natural mismatch or unhealthy condition, report those scenarios as covered
by unit tests only. Do not create one by mutating persistent intent or a device.

## Failure Evidence

Use only an explicitly authorized, reversible, non-mutating connectivity interruption if the owner
approves it. Otherwise rely on mocked boundary tests for timeout/unreachable behavior. In either
case, confirm inventory and retained history remain visible and both current observations become
unavailable without an automatic retry. Confirm the result identifies healthy intent provenance and
unavailable device provenance rather than collapsing both sources into one status.

## Record Results

Record exact commands, platform, observed source versions, pass/fail counts, natural canonical
states, unavailable scenarios, browser viewport evidence, and any unverified assumptions in the
project validation documentation. Never report an unobserved mismatch or health condition as
canonical success.
