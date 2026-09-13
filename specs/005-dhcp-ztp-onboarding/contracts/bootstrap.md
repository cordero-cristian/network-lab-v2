# Native Bootstrap Contract

## Gate

**Status**: DEFERRED — BLOCKED ON ACCESS TO A GENUINE BOOTABLE SR LINUX RUNTIME

Feature 005 may resume only when the owner provides or authorizes a genuine bootable SR Linux
artifact whose provenance and lab use are acceptable and which can exercise the documented
SR Linux auto-boot path. This contract remains inactive until that artifact passes the gate.

The accepted OCI container remains canonical for Features 001-004 and is never modified to
simulate ZTP. SR OS/vSIM, generic startup mounts, manually started ZTP, and unsupported
hardware-image emulation do not satisfy this contract.

## Network

- DHCP and HTTP run in one test-owned Linux container with Compose `network_mode: none`.
- The service has one explicit veth/bridge path only to the genuine guest's boot-management
  adapter. Hypervisor host-only/isolated networking must not enslave a physical interface.
- No published port, host/physical/macvlan link, default Compose network, unrelated lab
  network, IP forwarding, NAT, DNS forwarding, or upstream resolver is allowed.
- dnsmasq binds only that interface, uses one MAC-keyed deterministic infinite lease,
  disables DNS with `port=0`, and emits bounded DHCP diagnostics.
- The HTTP server binds only the same test-owned address and serves a fixed read-only root.

## DHCP Selection

The first genuine-runtime probe uses documented Options 66+67 or a complete literal-IPv4 HTTP
URL in Option 67. The exact selected form, bytes, and precedence are gate-derived. Option 43
is prohibited unless selected-runtime or authoritative vendor evidence supplies its exact
encoding; it is never guessed.

The offer includes the runtime-required subnet mask, router if needed, infinite lease, server
identifier, and script location. The deterministic boot-management MAC keys the lease. Packet
evidence must prove the same MAC in the link-layer request and Option 61. The runtime must use
Nokia's documented boot/GRUB client-ID MAC selection; host packet rewriting is prohibited.

## Served Material

The deterministic Python script executed by native ZTP:

1. Imports `ztpclient.APIClient`.
2. Calls `configure()` with the fixed startup JSON URL.
3. Requires returned `status == 0`.
4. Calls `option_autoboot(ztpclient.ZtpStatus.disable)`.
5. Requires returned `status == 0` and exits nonzero otherwise.

The fixed JSON establishes only exact hostname, deterministic management needs, and the
minimum authenticated gNMI service state proved necessary. Both files are deterministic, at most 64 KiB,
and contain no credentials, loopback, fabric address, BGP, routing policy, production
service, arbitrary command, dynamic template, or production artifact content.

## Completion Evidence

DHCP ACK, lease presence, HTTP GET, script exit, or gate success alone is insufficient.
Bootstrap readiness for each device requires all of:

- Exact minimum configuration observed through gate-proven authenticated post-boot reads;
  because the script disables auto-boot only after checked `configure()` success, this proves
  native script/configuration completion.
- Native auto-boot observed disabled through a gate-proven authenticated post-boot read.
- Authenticated gNMI Capabilities advertises `srl_nokia-system`.
- Gate-proven server-side lab authentication is available without credentials in the served
  script/configuration; client credentials exist only in runtime settings.
- Exact native hostname equals the mapped Nautobot Device name.
- Exact boot-management MAC equals DHCP evidence, the runtime-proven post-boot value, and the
  directly owned Nautobot `mgmt0` Interface MAC.
- Lease address equals Nautobot `primary_ip4` and is the authenticated gNMI target.

## Persistence

The gate records native startup storage and auto-boot state before and after a real guest
reboot and clean recreation. Successful ZTP must persist minimum configuration and disabled
auto-boot without `containerlab save` or a hypervisor snapshot. After later Feature 004
deployment, the test lifecycle may use native `tools system configuration save` only if the
gate proves it is needed for gNMI-applied intended configuration.
