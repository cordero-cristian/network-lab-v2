# Planning And Architecture Review: DHCP/ZTP Bootstrap And Automated Onboarding

**Reviewed**: 2026-09-12

**Status**: DEFERRED — BLOCKED ON ACCESS TO A GENUINE BOOTABLE SR LINUX RUNTIME

## Requirement Completeness

- [x] CHK001 Are all four prioritized stories independently testable with explicit success and failure acceptance scenarios? [Completeness, Spec §User Scenarios]
- [x] CHK002 Are genuine-runtime availability, native ZTP, MAC identity, minimum bootstrap, authentication, persistence, and reboot uncertainties explicitly defined as future gate measurements rather than assumptions? [Completeness, Spec §FR-005-FR-016]
- [x] CHK003 Are bootstrap ownership and forbidden production-intent boundaries exhaustive and consistent with Features 002 and 004? [Completeness, Spec §FR-001-FR-004]
- [x] CHK004 Are DHCP/HTTP reachability, optional Compose-overlay gating, service health, lifecycle, and teardown requirements all specified? [Completeness, Spec §FR-008-FR-010, FR-036-FR-039]
- [x] CHK005 Are runtime acquisition, mapping, readiness, handoff, duplicate, reboot, and diagnostic requirements represented in the 48 dependency-ordered tasks? [Traceability, Spec §FR-005-FR-052]

## Requirement Clarity

- [x] CHK006 Is genuine native ZTP distinguished unambiguously from startup configuration, bind mounts, topology injection, and container execution? [Clarity, Spec §FR-005-FR-007]
- [x] CHK007 Is bootstrap completion defined by per-device reads of disabled auto-boot and exact minimum state plus authenticated gNMI, hostname, MAC, address, and Nautobot agreement rather than gate or DHCP/HTTP evidence alone? [Clarity, Spec §FR-011-FR-016]
- [x] CHK008 Is the selected no-onboarding-event handoff explicit about unchanged deployment events and the accepted lack of replacement-incarnation protection? [Clarity, Spec §Clarifications, FR-018-FR-020]
- [x] CHK009 Are duplicate guarantees scoped specifically to redelivery of the same request event rather than independently generated requests? [Clarity, Spec §FR-026-FR-027]
- [x] CHK010 Are all timing, retry, artifact-size, identity-size, command-result, and acceptance bounds objectively stated in the spec or design contracts? [Measurability, Spec §Success Criteria]

## Requirement Consistency

- [x] CHK011 Do the spec, plan, data model, contracts, quickstart, and tasks consistently add no onboarding Kafka topic, event contract, workflow, daemon, or datastore? [Consistency, Spec §FR-018-FR-026]
- [x] CHK012 Does every artifact preserve Nautobot authority, Kafka transport, Temporal durable execution, Feature 002 sole rendering, and Feature 004 deployment/validation? [Consistency, Spec §FR-001]
- [x] CHK013 Are credentials consistently runtime-only and excluded from script, JSON, events, history, logs, output, and evidence? [Consistency, Spec §FR-034-FR-035]
- [x] CHK014 Is virtual identity consistently defined as the runtime-proven boot-management MAC mapped by core Nautobot Interface data, while physical serial use remains separate? [Consistency, Spec §FR-014-FR-016]
- [x] CHK015 Is the exact Feature 004 hostname equality guard preserved as a final pre-Set check without being represented as stable physical-incarnation protection? [Consistency, Spec §FR-013]

## Scenario Coverage

- [x] CHK016 Are primary blank boot, mapping, existing-path deployment, duplicate delivery, retrieval, renewal, reboot, and safe failure scenarios all covered? [Coverage, Spec §User Scenarios]
- [x] CHK017 Are unknown/duplicate identity, missing Nautobot data, service outage, readiness exhaustion, authentication, hostname/identifier/address mismatch, and partial native failure specified? [Coverage, Spec §Edge Cases, FR-041]
- [x] CHK018 Are restart and destroy/recreate explicitly distinguished so ephemeral recreation cannot be mistaken for reboot persistence? [Edge Case, Spec §Edge Cases]
- [x] CHK019 Are failure responsibilities before and after Kafka acceptance clearly separated between finite command output and existing durable deployment outcomes? [Exception Flow, Spec §FR-019-FR-025]
- [x] CHK020 Are excluded replacement/RMA, production DHCP/IPAM/security, rollback, API/UI, monitoring, HA, cloud, and generic provisioning concerns explicit? [Scope, Spec §FR-045]

## Evidence And Governance

- [x] CHK021 Are SC-001 through SC-014 measurable through named artifact-gate, offline, component, real-infrastructure, reboot, redaction, cleanup, and regression tasks? [Acceptance Criteria, Spec §Success Criteria]
- [x] CHK022 Are T003-T006 clearly separated as a future artifact/runtime gate with explicit failure/material-difference stop and owner review? [Governance, Plan §Blocked Implementation Sequence]
- [x] CHK023 Is the absence of a selected VM artifact and therefore unknown hypervisor/resource tuple documented without claiming unperformed success? [Evidence, Plan §Technical Context]
- [x] CHK024 Are test-owned cleanup boundaries and preservation of shared volumes, topics, namespaces, histories, unrelated labs, and user work explicit? [Safety, Spec §FR-038, SC-011]
- [x] CHK025 Is implementation approval clearly separate from completed planning, with no source, topology, runtime, commit, push, or persistent reset authorized? [Governance, Plan §Status]

## Accepted Gate And Redesign

- [x] CHK026 Does research classify every planned native-ZTP, option, artifact, identity,
  address, completion, boot, and persistence assumption as proven, disproven, modified, or
  still unverified? [Evidence, Research §Assumption Classification]
- [x] CHK027 Do all artifacts preserve accepted T001/T002 evidence while stopping T003 onward
  because no accessible genuine runtime is selected? [Consistency, Spec §FR-047-FR-048]
- [x] CHK028 Are Option 67 and malformed/retrieval behavior reported as unreachable and still
  unverified rather than falsely accepted or rejected? [Evidence, Research §1]
- [x] CHK029 Is `containerlab save` preserved as historical container evidence but prohibited
  from native ZTP persistence and genuine-runtime acceptance? [Boundary, Research §16]
- [x] CHK030 Are test-owned cleanup and preservation of normal lab resources documented from
  before/after observations? [Safety, Research §Security And Cleanup]

## Genuine Runtime Redesign

- [x] CHK031 Is a genuine runtime defined by firmware/bootloader, persistent boot storage,
  native auto-boot, DHCP, Python execution, and guest reboot rather than product name alone?
  [Clarity, Spec §FR-005, FR-049]
- [x] CHK032 Are the OCI container, SR OS/vSIM, generic startup mounts, manual ZTP start, and
  unsupported hardware-image emulation explicitly excluded? [Scope, Spec §FR-006, FR-048]
- [x] CHK033 Does the acquisition gate require artifact provenance, permitted use, exact pin,
  virtualization/resources, console evidence, and clean teardown? [Completeness, Spec §FR-047,
  SC-013]
- [x] CHK034 Do requirements mandate honest deferral when no practical genuine artifact is
  available instead of assuming VM support? [Evidence, Spec §FR-048]
- [x] CHK035 Are Options 66+67 and Option 67 distinguished from undocumented Option 43
  encoding, with exact behavior deferred to runtime evidence? [Clarity, Spec §FR-049]
- [x] CHK036 Is MAC stability required across DHCP, post-boot observation, guest reboot,
  clean recreation, and Nautobot mapping? [Consistency, Spec §FR-010-FR-016]
- [x] CHK037 Is the exact Nautobot 2.4.41 core Interface representation, non-unique field,
  all-candidate visibility, limit-two lookup, and post-validation contract complete?
  [Completeness, Data Model §Onboarding Mapping]
- [x] CHK038 Are a Nautobot App, identity database, external inventory, and generic identity
  abstraction excluded, with a Device custom field requiring separate approval? [Scope,
  Spec §FR-016]
- [x] CHK039 Are native auto-boot disable, configuration persistence, guest reboot, optional
  native save, and prohibition of snapshots/containerlab save unambiguous? [Consistency,
  Spec §FR-030-FR-031, FR-050]
- [x] CHK040 Does the separate genuine-runtime topology leave accepted Features 001-004
  container behavior and all render/deploy/validate ownership unchanged? [Architecture,
  Spec §FR-001, FR-021, FR-046]
- [x] CHK041 Is the unblock condition consistently limited to an owner-provided or authorized
  genuine bootable SR Linux artifact with acceptable provenance/lab use that can exercise the
  documented auto-boot path? [Governance, Spec §Status]
