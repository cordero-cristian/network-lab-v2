# Quickstart And Acceptance Plan

**Status**: DEFERRED — BLOCKED ON ACCESS TO A GENUINE BOOTABLE SR LINUX RUNTIME

**Unblock condition**: Feature 005 may resume only when the owner provides or authorizes a
genuine bootable SR Linux artifact whose provenance and lab use are acceptable and which can
exercise the documented SR Linux auto-boot path. Until then, do not run T003-T048 or the
commands below the accepted T001/T002 evidence.

## Host Prerequisites

Use canonical Ubuntu 24.04.4 x86-64 with hardware virtualization, an owner-authorized genuine
bootable SR Linux artifact, its documented hypervisor/firmware/NIC/resource requirements,
Docker for isolated DHCP/HTTP and existing services, `uv`, `jq`, console capture, and packet
capture on test-owned links. The exact VM prerequisites remain unknown until T003.

Do not run DHCP experiments on a host, physical, macvlan, default Compose, or shared lab
network.

## Accepted Container Gate

T001 used multiple disposable raw-containerlab probes, including a two-node identity probe
and isolated in-band/OOB discovery probes with `suppress-startup-config: true`, no
hostname/config injection, and a `network-mode: none` bootstrap container connected by an
explicit veth. The gate observed rather than assumed:

- Native DHCP discovery and exact interface.
- Option 61 identity and option 67 retrieval behavior.
- Native `ztpclient` execution and accepted startup JSON.
- Runtime-provided authenticated gNMI and exact serial path/value.
- Auto-boot disabled state and startup configuration persistence.
- Restart and destroy/recreate behavior.
- No DHCP/HTTP binding or traffic outside the test link.

Observed: clean stop under FR-006. The pinned container emitted no DHCP discovery on isolated
in-band or OOB links and exposed no unique chassis serial. No alternate DHCP option, startup
config, bind-mounted device config, manually started ZTP process, or `exec` provisioning was
substituted. This evidence is accepted; the container remains canonical for Features 001-004.

## Future Genuine-Runtime Gate

Do not run T003-T006 until the owner supplies or authorizes an exact bootable SR Linux
artifact and explicitly approves the gate. Record provenance, permitted use, release/digest,
hypervisor, firmware, machine/NIC model, vCPU/RAM/disk, console, and cleanup. Then prove:

- Firmware/bootloader and persistent boot storage reach documented SR Linux auto-boot.
- A vendor-supported boot option selects MAC client identity; native DHCP carries the
  deterministic boot-management MAC in proven link-layer and Option 61 forms and receives the
  exact static lease.
- Documented Options 66+67 or complete Option 67 retrieves and executes the Python script.
- Native `configure()` applies only the minimum state and checked auto-boot disable succeeds.
- Authenticated gNMI becomes available through selected-runtime factory lab authentication or
  another vendor-supported native mechanism without credentials in served artifacts; client
  credentials remain runtime-only.
- The same MAC is observable after startup and stable through guest reboot and clean recreation.
- Authenticated post-boot reads expose disabled auto-boot and every exact minimum configuration
  value needed for the finite boundary to prove this device completed native bootstrap.
- Minimum state and disabled auto-boot persist through a real guest reboot without
  `containerlab save` or hypervisor snapshot.
- One test-owned post-operational gNMI change is applied and rebooted without save; if it is
  lost, repeat with native `tools system configuration save` and record the exact requirement.
- DHCP remains confined to the test-owned virtual link and teardown removes only gate resources.

If any item fails or no artifact is available, update evidence and stop. Hardware-targeted
media under generic QEMU, SR OS/vSIM, the OCI container, startup mounts, and manually started
ZTP do not qualify.

## Offline Validation

Only after T006 reconciliation and explicit implementation approval, run:

```sh
uv sync --locked
uv run pytest
uv run pytest tests/unit/test_bootstrap_contract.py tests/unit/test_onboarding_cli.py
uv run pytest tests/unit/test_nautobot_onboarding.py tests/unit/test_srlinux_device.py
uv build
docker compose config --quiet
docker compose -f compose.yaml -f compose.bootstrap.yaml config --quiet
docker compose -f compose.yaml -f compose.device-access.yaml config --quiet
```

Expected after a passing gate and implementation approval: deterministic bounded inputs,
forbidden-content rejection, exact bootstrap-MAC mapping,
readiness classification, redaction, no premature event, byte-stable publication, network
isolation, safe lifecycle, and every existing unit/replay test pass. Explicit integration
selection without dependencies must fail rather than skip.

## Start Order

1. Start and initialize the existing Feature 001 supporting stack.
2. Start only the isolated bootstrap service and verify its meaningful health.
3. Boot the separate genuine-runtime topology with its deterministic management-adapter MAC;
   leave the accepted Features 001-004 container topology unchanged.
4. Observe target DHCP/script/native status and independently inspect bootstrap-only state.
5. Attach/start the existing automation worker and consumer through approved device access.
6. Inject runtime-only device credentials and run `network-onboard-device BOOTSTRAP_MAC`.

Do not proceed to handoff unless bootstrap-only inspection finds exact hostname,
management/authenticated gNMI, disabled native auto-boot, exact minimum state, and bootstrap-MAC agreement, while loopback, fabric addresses, BGP,
policy, and production services remain absent.

## End-To-End Acceptance

The test entry points are planned, but the exact hypervisor lifecycle command cannot be
specified until T003 selects an artifact:

```sh
uv run pytest tests/integration/test_srlinux_ztp_boot.py
uv run pytest tests/integration/test_srlinux_onboarding.py
```

The onboarding acceptance creates only uniquely marked test-owned Nautobot objects with a
directly Device-owned `mgmt0` Interface carrying the bootstrap MAC, plus the existing name,
platform, and `primary_ip4`. It proves:

- Blank boot through genuine firmware/GRUB auto-boot and native replay prevention.
- DHCP/runtime/Nautobot management-MAC equality and deterministic management-address equality.
- Authenticated gNMI, native model, and exact hostname before Kafka publication.
- Existing Kafka -> Temporal -> Nautobot -> Feature 002 render -> Feature 004 deploy/Get ->
  correlated deployment result, without a new event topic or workflow.
- Native minimum state and disabled auto-boot survive guest reboot without a lab save.
- If T005 proved later gNMI state is running-only, the test lifecycle invokes native
  `tools system configuration save` after successful deployment and before guest reboot.
- Independent final hostname, interface, address, ASN, peer, and BGP-established state.
- Duplicate request delivery, lease renewal, and repeated retrieval create one logical result
  and do not alter intended state.
- Unknown/duplicate MAC, missing device, outage, timeout, authentication, hostname, MAC,
  and address mismatch fail safely before mutation where identity is untrusted.
- Final configuration and manageability survive one reboot with no destructive re-bootstrap.
- Credentials and raw bootstrap/production content are absent from events, Temporal history,
  normal logs, command output, and retained evidence.

Fixtures delete only exact created Nautobot records and local artifacts. Kafka records and
Temporal history remain as durable evidence. No shared topic, namespace, or volume is reset.

## Regression

```sh
uv run network-lab-check
uv run pytest tests/integration/test_services.py
uv run pytest tests/integration/test_nautobot_render.py
uv run pytest tests/integration/test_event_components.py
uv run pytest tests/integration/test_event_driven_render.py
uv run pytest tests/integration/test_srlinux_deployment.py
```

Record exact commands, versions, image digest, platform, counts, observations, failures, and
cleanup in `docs/validation.md`. Review for one package, existing worker/consumer/workflow,
Feature 002 sole rendering, Feature 004 unchanged pre-Set guard, and absence of new topics,
datastores, generic provisioning frameworks, or excluded features.

## Safe Teardown

Stop the onboarding command, remove the worker endpoint from test-owned networks, shut down
and remove the disposable guest definition/storage overlay, and remove the bootstrap
service/link. Verify test-owned DHCP/HTTP, bridges/veths/taps, guest processes, captures, and
temporary network state are gone without deleting the authorized source artifact.
Unset device credentials. Restore the base automation services if they were recreated.

Supporting named volumes, Kafka topics/records, Temporal namespace/history, unrelated labs,
host networking, and physical interfaces must remain unchanged.
