# Feature Specification: Read-only Drift and Compliance Detection

**Feature Branch**: `007-read-only-drift-compliance`

**Created**: 2026-09-22

**Status**: Implementation and canonical acceptance completed on 2026-09-23

**Input**: User description: "Add read-only drift and compliance detection from Nautobot intended state and structured live SR Linux reads, keep configuration drift separate from operational health, expose the results through the existing operator UI, and stop for architectural review before implementation."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Identify Expected Configuration Drift (Priority: P1)

As a lab operator, I can request a current comparison for one device and see whether each supported expected configuration fact from Nautobot matches the device, without treating operational failures as configuration drift.

**Why this priority**: The core feature value is a trustworthy answer to whether supported intended configuration is present and equal on the device.

**Independent Test**: Request a comparison for a device whose supported intended values are known, then verify that matching values report in sync and changed or absent expected values report drift, with each result traceable to Nautobot intent and the same bounded live observation.

**Acceptance Scenarios**:

1. **Given** every supported expected configuration fact matches the live device, **When** the operator requests a comparison, **Then** configuration status is in sync and every configuration check shows the matching expected and observed evidence.
2. **Given** one supported expected hostname, administrative state, address, local autonomous-system number, or neighbor peer autonomous-system number is changed or absent, **When** the comparison completes, **Then** configuration status is drifted and the exact mismatching expected fact is identified.
3. **Given** configured BGP neighbor attributes match intent but the BGP session is down, **When** the comparison completes, **Then** configuration remains in sync while operational health reports the failed session separately.
4. **Given** an expected address is present but not operationally ready, **When** the comparison completes, **Then** address presence is not reported as drift and address readiness is reported separately as unhealthy.

---

### User Story 2 - Assess Operational Health Separately (Priority: P1)

As a lab operator, I can see whether the expected interfaces, addresses, and BGP sessions are operationally healthy without that result changing the configuration-drift decision.

**Why this priority**: Operators must distinguish incorrect configuration from correctly configured services that are currently down or converging.

**Independent Test**: Observe a device whose supported configured values match intent while one operational value is unhealthy, and verify that the health result degrades independently while drift remains in sync.

**Acceptance Scenarios**:

1. **Given** all supported operational facts for expected objects are healthy, **When** the operator requests a comparison, **Then** operational health is healthy.
2. **Given** an expected interface or subinterface is down, an expected address is not ready, or an expected BGP session is not established, **When** the comparison completes, **Then** operational health is degraded and identifies the unhealthy fact without creating a drift check failure.
3. **Given** an expected object is absent and therefore has no operational state, **When** the comparison completes, **Then** its configuration check reports drift and its health check reports unavailable rather than inventing an operational failure.

---

### User Story 3 - Inspect Trustworthy Results in Device Detail (Priority: P2)

As a lab operator, I can inspect configuration drift and operational health as separate, clearly sourced sections in the existing device detail experience.

**Why this priority**: The distinction must remain visible at the presentation boundary rather than being collapsed into one validation or compliance badge.

**Independent Test**: Open one device detail view and verify that intended state, configuration drift, operational health, source availability, and observation time remain distinguishable on desktop and narrow viewports, with no mutation action available.

**Acceptance Scenarios**:

1. **Given** a current comparison is available, **When** device detail is displayed, **Then** separate configuration-drift and operational-health summaries show their own status, check counts, evidence, source, and common live observation time.
2. **Given** Nautobot intent or the device read is unavailable or times out, **When** device detail is displayed, **Then** both results clearly show unavailable source evidence while independent inventory and retained automation history remain usable.
3. **Given** no live comparison was requested, **When** device detail is displayed or refreshed from non-device sources, **Then** no drift or health conclusion is fabricated and no device read occurs automatically.
4. **Given** any displayed result, **When** the operator inspects the page and available actions, **Then** no remediation, deployment, edit, acknowledgment, exception, or policy-management control is present.

### Edge Cases

- Nautobot intent can be malformed, incomplete, or unavailable while inventory identity remains available.
- The device can be unreachable, reject authentication, return malformed data, or exceed the existing live-read deadline.
- A supported expected leaf can be absent, have the wrong scalar type, or return an unknown value.
- An expected address can exist at the exact intended key while its readiness state is not healthy.
- A configured BGP peer can have the intended peer autonomous-system number while its session is idle, active, or otherwise not established.
- Some checks can be assessable while operational state for other expected objects is unavailable.
- Repeated expected values are rejected by the authoritative intent boundary rather than deduplicated during comparison.
- Device state can change immediately after observation; every result therefore needs one explicit observation time and must not claim continuous truth.
- Unexpected extra interfaces, addresses, neighbors, or other configuration can exist and remain intentionally unreported in v1.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The feature MUST be read-only and MUST NOT render, deploy, remediate, edit, acknowledge, suppress, approve, or otherwise mutate intended state, device state, automation state, or infrastructure.
- **FR-002**: Nautobot MUST remain the sole authority for intended state; live device data MUST be observation evidence only and MUST NOT become or override intent.
- **FR-003**: The feature MUST derive expected comparison values from the accepted normalized device-intent model and MUST NOT reconstruct intent from rendered configuration or artifacts.
- **FR-004**: The feature MUST produce one explicit configuration-drift result and one separate operational-health result from one bounded live observation of one selected device.
- **FR-005**: The operator-visible configuration-drift observation status MUST be `in_sync`, `drifted`, or `unavailable`; it MUST be `drifted` when at least one supported expected configuration check mismatches, `in_sync` only when every required check matches, and `unavailable` with no nested result when a trustworthy comparison cannot be completed.
- **FR-006**: Operational-health status MUST be `healthy`, `degraded`, or `unavailable`; it MUST be `healthy` only when every supported health check is healthy, `degraded` when at least one assessable check is unhealthy or unavailable while other evidence remains assessable, and `unavailable` when no supported health check can be assessed.
- **FR-007**: V1 configuration drift MUST compare only expected hostname, expected interface and subinterface administrative enablement, expected IPv4 address presence at each exact intended prefix, expected local BGP autonomous-system number, and expected peer autonomous-system number for each intended BGP neighbor.
- **FR-008**: V1 operational health MUST assess only expected interface and subinterface operational state, expected IPv4 address readiness, and expected BGP neighbor session state.
- **FR-009**: Interface or subinterface operational state MUST NOT affect configuration-drift status.
- **FR-010**: BGP session state MUST NOT affect configuration-drift status; a down BGP session with matching local and peer autonomous-system configuration MUST remain configuration in sync.
- **FR-011**: An exact expected address observed with a non-healthy readiness value MUST count as present for configuration comparison and unhealthy for operational health; an absent expected address MUST report configuration drift and unavailable health for that address.
- **FR-012**: Every check MUST identify a stable check key, supported category, status, expected value, observed value when available, and a bounded safe explanation when it does not pass.
- **FR-013**: Configuration checks MUST use only `match` or `mismatch`; operational checks MUST use `healthy`, `unhealthy`, or `unavailable`. The two check taxonomies MUST NOT be combined into one pass/fail list.
- **FR-014**: V1 MUST inspect expected objects only and MUST NOT enumerate or classify unexpected extra device configuration.
- **FR-015**: V1 MUST NOT introduce a generic policy, rule, control, exception, waiver, scoring, severity, or compliance-framework abstraction; compliance means only whether the bounded expected configuration checks are in sync.
- **FR-016**: The live observation MUST reuse the accepted structured SR Linux read boundary and MUST NOT introduce a second device client or an additional device read for the same comparison request.
- **FR-017**: A device-detail request MAY perform exactly one on-demand live observation with the accepted 15-second operation budget; overview, list, scheduled refresh, and background work MUST NOT read devices.
- **FR-018**: The feature MUST NOT add continuous telemetry, subscriptions, streaming, background device polling, or automatic live retries.
- **FR-019**: Results MUST be transient projections and MUST NOT add a datastore, cache, durable compliance record, event consumer, workflow, or new source of truth.
- **FR-020**: Configuration drift and operational health MUST each carry separate Nautobot-intent and device-read availability plus the same UTC comparison timestamp; successful nested results MUST also share that timestamp.
- **FR-021**: An unavailable intent or live source MUST produce explicit unavailable results and MUST NOT be interpreted as drift, in-sync configuration, healthy operation, or an empty check set.
- **FR-022**: Missing expected configuration MUST remain configuration drift even when corresponding operational state is unavailable.
- **FR-023**: Observed leaves MUST satisfy their canonical scalar types before comparison. A wrong value of the correct type MAY be drift or unhealthy, but a wrong scalar type, empty text, or unbounded text MUST make the entire current comparison unavailable, remain sanitized, and MUST NOT expose raw device responses, credentials, rendered configuration, or exception details.
- **FR-024**: The existing operator device-detail view MUST present intended state, configuration drift, and operational health as distinct sections with status text and non-color indicators, check counts, per-check evidence, source availability, and observation time.
- **FR-025**: The presentation MUST NOT collapse the two results into one overall compliance, validation, or health status.
- **FR-026**: Existing retained deployment validation MUST remain identifiable as historical deployment evidence and MUST NOT be relabeled as a current drift result.
- **FR-027**: Current comparison presentation MUST remain usable at desktop and 375-pixel viewport widths without horizontal page overflow and with keyboard-accessible navigation.
- **FR-028**: The browser MUST obtain results only through the existing bounded read-only service boundary and MUST NOT connect directly to Nautobot or a device.
- **FR-029**: The read service and interface MUST expose no mutation route, method, control, or future-action placeholder associated with drift or health.
- **FR-030**: Unit tests MUST prove every supported matching, mismatch, unhealthy, unavailable, malformed-type, and aggregate-status rule independently, including the rule that BGP-down is not drift and the rule that malformed leaves make both current observations unavailable rather than producing false drift or health.
- **FR-031**: Real-infrastructure acceptance MUST compare current Nautobot intent and one real structured SR Linux observation without mutating either source solely to manufacture evidence.
- **FR-032**: Existing Features 001-004 automation behavior and Feature 006 read-only, timeout, polling, security, and responsive-presentation guarantees MUST remain healthy.
- **FR-033**: Deferred Feature 005 MUST remain unchanged and outside this feature's runtime and acceptance paths.
- **FR-034**: Automated API tests MUST prove exactly one device read for a successful `live=true` request, zero reads for `live=false` and unavailable intent, and no automatic retry after success, timeout, or failure.
- **FR-035**: Automated comparison tests MUST prove that unrelated or unexpected observed mapping keys create no checks and do not change either result.

### Key Entities

- **Comparison Observation**: One transient, timestamped pairing of normalized Nautobot intent and one bounded structured device read for one device; it supplies common provenance to both results.
- **Configuration Drift Observation**: Operator-facing `in_sync`, `drifted`, or `unavailable` conclusion with separate intent/device source evidence and an optional successful configuration result.
- **Configuration Drift Result**: Successful `in_sync` or `drifted` comparison over only supported expected configuration checks.
- **Configuration Check**: One expected configuration fact with a stable key, category, `match` or `mismatch` status, expected value, optional observed value, and safe explanation.
- **Operational Health Observation**: Operator-facing `healthy`, `degraded`, or `unavailable` conclusion with separate intent/device source evidence and an optional successful operational result.
- **Operational Health Result**: Successful comparison aggregate over only supported health checks for expected objects; it may itself be unavailable when every expected object's health leaf is absent.
- **Operational Health Check**: One expected object's operational fact with a stable key, category, `healthy`, `unhealthy`, or `unavailable` status, desired condition, optional observed value, and safe explanation.
- **Source Availability**: Existing source-specific state that explains whether Nautobot intent and the live device observation were available without substituting a domain conclusion.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every supported matching configuration fixture, 100% of configuration checks report `match` and the aggregate reports `in_sync`.
- **SC-002**: For each supported expected configuration field, changing or removing only that field causes exactly the corresponding configuration check to report `mismatch` and the aggregate to report `drifted`.
- **SC-003**: In 100% of tests where configured BGP values match but session state is not established, configuration reports `in_sync` and operational health reports `degraded`.
- **SC-004**: In 100% of tests where an expected address is observed at its exact key but is not ready, its configuration check reports `match` and its health check reports `unhealthy`.
- **SC-005**: An operator can identify whether a current issue is configuration drift, operational health, both, or unavailable within 10 seconds of opening a populated device-detail result.
- **SC-006**: Every current result displayed to the operator is traceable to Nautobot intent and one live observation timestamp, with zero conclusions reconstructed from rendered artifacts.
- **SC-007**: Device read timeout and source-failure tests terminate within the accepted request bound and produce zero false drift, in-sync, or healthy conclusions.
- **SC-008**: Repository and runtime inspection finds zero new datastores, policy engines, telemetry subscriptions, event consumers, remediation paths, or background device pollers.
- **SC-009**: API and browser inspection finds zero raw configuration, raw device responses, credentials, unrestricted paths, or mutation controls.
- **SC-010**: Configuration and health sections remain readable and navigable at desktop and 375-pixel viewport widths without horizontal page overflow.
- **SC-011**: All existing automated Feature 001-006 regression checks pass after the feature is added, in addition to the new drift and health checks.
- **SC-012**: Automated route tests observe exactly one device-read call for each successful on-demand comparison and zero calls for unrequested or intent-unavailable comparisons, with zero automatic retry calls.
- **SC-013**: Adding unexpected observed-state keys changes zero configuration checks, zero health checks, and zero aggregate statuses in 100% of expected-only scope tests.

## Assumptions

- The v1 comparison is an on-demand current observation for one selected device, not historical drift tracking or fleet-wide scanning.
- Existing normalized device intent contains all v1 expected values; descriptions, roles, locations, and unsupported platform-specific settings are not drift checks.
- An exact keyed address-status observation proves that the expected address is present even when its readiness value is unhealthy; valid absence means the expected address is missing.
- Existing structured reads expose the configuration and operational facts required by the bounded v1 scope without another device request.
- Unexpected extra configuration is explicitly out of scope for v1 because the current bounded read is driven by expected objects and does not enumerate device configuration.
- Historical Feature 004 validation can remain combined deployment-time evidence; only the new current comparison must expose separate drift and health results.
- The trusted-lab access, source availability, no-store response, timeout, and one-shot live-read assumptions accepted for Feature 006 continue to apply.
