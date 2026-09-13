---

description: "Implementation tasks for genuine SR Linux ZTP and automated onboarding"
---

# Tasks: DHCP/ZTP Bootstrap And Automated Onboarding

**Input**: Design documents from `specs/005-dhcp-ztp-onboarding/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, an
owner-authorized genuine bootable SR Linux artifact, and explicit gate/implementation approval

**Tests**: Required. Unit tests mock boundaries; canonical acceptance uses real isolated
infrastructure and the exact selected runtime.

**Status**: DEFERRED — BLOCKED ON ACCESS TO A GENUINE BOOTABLE SR LINUX RUNTIME

T001-T002 are complete. T003-T048 are deferred and blocked, not failed or complete, and MUST
NOT run without explicit approval. T003-T006 are a replacement runtime gate, not feature
implementation.

**Unblock condition**: Feature 005 may resume only when the owner provides or authorizes a
genuine bootable SR Linux artifact whose provenance and lab use are acceptable and which can
exercise the documented SR Linux auto-boot path.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel only after its phase dependencies pass
- **[Story]**: User story traceability label
- Every task names the files it creates or changes

## Phase 1: Accepted Container Evidence

**Purpose**: Preserve the evidence that the canonical container is not a genuine ZTP boot runtime

- [x] T001 Run the disposable Ubuntu x86-64 pinned-container native-ZTP proof and record process, DHCP/HTTP, serial, persistence, redaction, and cleanup evidence in `specs/005-dhcp-ztp-onboarding/research.md` and `docs/validation.md`
- [x] T002 Reconcile the failed container gate across `specs/005-dhcp-ztp-onboarding/` and stop before implementation

**Checkpoint**: T001/T002 accepted; the Features 001-004 container remains unchanged

---

## Phase 2: Genuine Runtime Gate

**Purpose**: Select and prove an accessible genuine SR Linux boot path before source implementation

**CRITICAL**: T003-T006 require separate approval. Any unavailable artifact, unsupported use,
missing boot path, unstable MAC, absent native DHCP/script execution, or material difference
stops the feature for artifact correction and owner review.

- [ ] T003 Record owner-authorized SR Linux artifact provenance, permitted lab use, release/digest, acquisition procedure without credentials, and vendor runtime requirements in `specs/005-dhcp-ztp-onboarding/research.md` and `lab/ztp-runtime/README.md`
- [ ] T004 Define a disposable artifact-specific Ubuntu x86-64 boot topology and evidence harness with isolated networking, console capture, and teardown in `lab/ztp-topology.yml` and `tests/integration/test_srlinux_ztp_boot.py`
- [ ] T005 Run the exact artifact gate to prove firmware/GRUB auto-boot, vendor-supported MAC client-ID selection, DHCP Option 61 MAC, Options 66+67 or 67, Python execution, minimum configuration, credential-free server-side authenticated gNMI establishment with runtime-only client credentials, post-boot reads for exact minimum state and disabled auto-boot, stable MAC, native persistence, and guest reboot; apply one test-owned post-operational gNMI change and determine persistence without save and then with native save if required; record runtime resources, cleanup, and results in `specs/005-dhcp-ztp-onboarding/research.md` and `docs/validation.md`
- [ ] T006 Reconcile every selected-runtime constant and material difference across `specs/005-dhcp-ztp-onboarding/spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`, and `tasks.md`, run consistency analysis, and stop for explicit implementation approval

**Checkpoint**: One genuine runtime is proven and pinned, or Feature 005 remains deferred

---

## Phase 3: Foundational Boundaries

**Purpose**: Establish only the runtime-proven bootstrap and MAC mapping boundaries

- [ ] T007 Add bounded onboarding/runtime settings and runtime-only credential validation in `src/network_automation/settings.py` and `.env.example`
- [ ] T008 [P] Add frozen strict MAC identity, runtime evidence, lease, artifact, mapping, readiness, accepted-result, and safe-failure models with tests in `src/network_automation/onboarding.py` and `tests/unit/test_onboarding_models.py`
- [ ] T009 [P] Add static isolation, no-public-DHCP, image/artifact pin, and unchanged canonical-topology checks in `tests/unit/test_automation_compose.py` and `tests/unit/test_device_topology.py`
- [ ] T010 Add the selected runtime's separately managed topology/network lifecycle while preserving `lab/topology.yml` in `lab/ztp-topology.yml` and `compose.bootstrap.yaml`
- [ ] T011 Run locked unit/build and Compose/topology validation, correcting only Feature 005 foundations in `pyproject.toml`, `compose.bootstrap.yaml`, and `lab/ztp-topology.yml`

---

## Phase 4: User Story 1 - Bootstrap A Blank Device Safely (Priority: P1) MVP

**Goal**: A genuine blank SR Linux boot reaches only identity and authenticated management

**Independent Test**: Observe firmware/GRUB auto-boot, isolated MAC-keyed DHCP, native script,
minimum state, disabled auto-boot, and authenticated gNMI with all production intent absent

- [ ] T012 [P] [US1] Write deterministic DHCP/options/script/config/path/size/credential/forbidden-content contract tests in `tests/unit/test_bootstrap_contract.py`
- [ ] T013 [P] [US1] Write isolated DHCP/HTTP health, MAC lease, repeated retrieval, binding, and no-public-DHCP component tests in `tests/integration/test_bootstrap_services.py`
- [ ] T014 [P] [US1] Write genuine-runtime blank-boot, deterministic adapter MAC, and unchanged container-topology assertions in `tests/unit/test_device_topology.py`
- [ ] T015 [US1] Implement the exact gate-proven MAC-static DHCP options and bounded diagnostics in `lab/bootstrap/dnsmasq.conf`
- [ ] T016 [P] [US1] Implement the gate-proven native Python provisioning script with checked configure and auto-boot-disable results in `lab/bootstrap/ztp.py`
- [ ] T017 [P] [US1] Implement the gate-proven minimum credential-free bootstrap configuration in `lab/bootstrap/bootstrap.json`
- [ ] T018 [US1] Add the isolated DHCP/HTTP service with `network_mode: none`, explicit test link, no forwarding, no published ports, and meaningful health in `compose.bootstrap.yaml`
- [ ] T019 [US1] Wire only the genuine runtime's boot-management adapter to the isolated service while leaving `lab/topology.yml` unchanged in `lab/ztp-topology.yml`
- [ ] T020 [US1] Prove genuine blank boot, native completion, minimum state, and DHCP isolation against the selected runtime in `tests/integration/test_srlinux_onboarding.py`

**Checkpoint**: US1 independently proves genuine native minimum bootstrap

---

## Phase 5: User Story 2 - Onboard Through Existing Automation (Priority: P2)

**Goal**: Map one boot-management MAC and hand the device to unchanged Features 002-004

**Independent Test**: Prove exact MAC/interface/device/name/address agreement, publish one
existing request, and observe the existing correlated render/deploy/validate result

- [ ] T021 [P] [US2] Write Nautobot Interface MAC normalization, duplicate/missing/hidden-result, direct ownership, role/name, platform, and primary-IP mapping tests in `tests/unit/test_nautobot_onboarding.py`
- [ ] T022 [P] [US2] Write native model, hostname, gate-proven MAC relation, disabled-auto-boot, exact-minimum-state, address, authentication, malformed-response, and pyGNMI-redaction tests in `tests/unit/test_srlinux_device.py`
- [ ] T023 [P] [US2] Write finite command no-event-before-readiness, existing-event shape, byte-stable producer retry, and safe output tests in `tests/unit/test_onboarding_cli.py`
- [ ] T024 [US2] Add exact core `/api/dcim/interfaces/` MAC lookup with limit-two cardinality and same-origin Device traversal in `src/network_automation/intent/nautobot.py`
- [ ] T025 [US2] Add credential-safe runtime-proven MAC, disabled-auto-boot, exact-minimum-state, and bootstrap-readiness reads without changing the Feature 004 pre-Set guard in `src/network_automation/devices/srlinux.py`
- [ ] T026 [US2] Implement the shared 90-second mapping/readiness boundary requiring per-device native completion state and safe classification in `src/network_automation/onboarding.py`
- [ ] T027 [US2] Implement `network-onboard-device BOOTSTRAP_MAC` and existing `DeploymentRequested` publication in `src/network_automation/cli/onboard.py`, `src/network_automation/events/producer.py`, and `pyproject.toml`
- [ ] T028 [US2] Extend test-owned Nautobot fixtures with direct `mgmt0` MAC and management relationships in `tests/integration/support/nautobot_fixture.py`
- [ ] T029 [US2] Prove genuine bootstrap through existing Kafka/Temporal/Feature 002/Feature 004 deployment and validation in `tests/integration/test_srlinux_onboarding.py`

**Checkpoint**: US2 proves authoritative core-MAC mapping and unchanged durable handoff

---

## Phase 6: User Story 3 - Repeat And Reboot Safely (Priority: P3)

**Goal**: Repetition and real guest reboot preserve intended state without ZTP re-entry

- [ ] T030 [P] [US3] Add byte-stability, lease-renewal, and repeated DHCP/HTTP retrieval tests in `tests/unit/test_bootstrap_contract.py` and `tests/integration/test_bootstrap_services.py`
- [ ] T031 [P] [US3] Add same-request-ID redelivery and closed-reuse assertions without changing Feature 003/004 semantics in `tests/unit/test_event_consumer.py` and `tests/integration/test_srlinux_onboarding.py`
- [ ] T032 [P] [US3] Add guest-reboot, disabled-auto-boot, native persistence, and no-snapshot acceptance cases in `tests/integration/test_srlinux_onboarding.py`
- [ ] T033 [US3] Enforce deterministic bootstrap bytes, MAC lease selection, and harmless repetition in `lab/bootstrap/ztp.py`, `lab/bootstrap/bootstrap.json`, and `lab/bootstrap/dnsmasq.conf`
- [ ] T034 [US3] Add a test-lifecycle native SR Linux configuration save only if T005 proved it necessary for post-deployment state in `tests/integration/test_srlinux_onboarding.py`
- [ ] T035 [US3] Prove same-request redelivery, lease renewal, repeated retrieval, one guest reboot, stable MAC, persisted state, BGP, and no second logical deployment in `tests/integration/test_srlinux_onboarding.py`
- [ ] T036 [US3] Assert `containerlab save` and hypervisor snapshots are absent from genuine-runtime acceptance in `tests/unit/test_device_topology.py`

---

## Phase 7: User Story 4 - Diagnose Failure Safely (Priority: P4)

**Goal**: Native bootstrap and MAC identity failures are bounded, categorized, and safe

- [ ] T037 [P] [US4] Add gate-proven native temporary/permanent failure bounds, no failed-bootstrap handoff, command mapping failure, durable retry, and safe-category tests in `tests/unit/test_bootstrap_contract.py`, `tests/unit/test_onboarding_cli.py`, and `tests/unit/test_srlinux_device.py`
- [ ] T038 [P] [US4] Add unknown/duplicate MAC, wrong Interface ownership, missing Device, bootstrap outage, readiness timeout, authentication, mismatch, and failed-reboot cases in `tests/integration/test_srlinux_onboarding.py`
- [ ] T039 [P] [US4] Add credential/raw-artifact/raw-response/console/packet/stack redaction assertions in `tests/unit/test_onboarding_cli.py` and `tests/integration/test_srlinux_onboarding.py`
- [ ] T040 [US4] Complete static safe failure mapping and bounded correlation/stage/MAC logging in `src/network_automation/onboarding.py`, `src/network_automation/cli/onboard.py`, and `src/network_automation/devices/srlinux.py`
- [ ] T041 [US4] Exercise bounded DHCP/HTTP/native-status/console diagnostics and assert they never enter events or workflow payloads in `tests/integration/test_srlinux_onboarding.py`
- [ ] T042 [US4] Prove failed native bootstrap leaves auto-boot retry behavior bounded and creates no Nautobot mutation, Kafka event, or Temporal history in `tests/integration/test_srlinux_onboarding.py`

---

## Phase 8: Documentation And Cross-Cutting Validation

- [ ] T043 [P] Document genuine-runtime acquisition prerequisites, isolated startup, diagnostics, runtime credentials, persistence, and safe teardown in `README.md`, `docs/network-lab.md`, and `lab/ztp-runtime/README.md`
- [ ] T044 [P] Add exact Feature 005 commands, evidence template, platform limitations, and redaction rules in `docs/validation.md`
- [ ] T045 Run the default suite and accepted-history Temporal replay in `tests/unit/test_render_workflow_replay.py`, correcting only Feature 005 regressions
- [ ] T046 Run Feature 001-004 component and canonical integration commands from `specs/005-dhcp-ztp-onboarding/quickstart.md` and record actual results in `docs/validation.md`
- [ ] T047 Run the complete genuine-runtime lifecycle, final inspection, guest reboot, failure matrix, and safe teardown from `specs/005-dhcp-ztp-onboarding/quickstart.md`; record evidence in `docs/validation.md`
- [ ] T048 Run `uv build`, Compose/topology checks, `git diff --check`, Spec Kit analysis, and both Feature 005 checklists in `specs/005-dhcp-ztp-onboarding/checklists/`

## Dependencies And Stop Rules

- T003 requires an owner-authorized artifact and explicit approval; no artifact means deferral.
- T004-T006 are serialized on the same runtime and must stop on any material difference.
- T007-T048 require a passing T006 reconciliation and separate implementation approval.
- US1 is the MVP. US2 requires US1; US3 requires US1/US2; US4 tests their boundaries.
- Tests in separate files marked `[P]` may proceed in parallel only after their gate.
- Real tests sharing the runtime/topology are always serialized.

## Implementation Strategy

1. Acquire and prove, never emulate.
2. Bootstrap only identity, hostname, management, authentication, and gNMI.
3. Map deterministic management MAC through core Nautobot Interface data.
4. Publish only the existing deployment request.
5. Let Features 002-004 render, orchestrate, deploy, and validate unchanged.
6. Prove real guest reboot and native persistence without `containerlab save` or snapshots.

No runtime execution, source implementation, or persistent reset is authorized. Planning
artifacts may be committed and pushed only under separate explicit owner direction.
