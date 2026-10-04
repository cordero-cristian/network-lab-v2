# Research: DHCP/ZTP Bootstrap And Automated Onboarding

**Date**: 2026-09-12

**Status**: DEFERRED — BLOCKED ON ACCESS TO A GENUINE BOOTABLE SR LINUX RUNTIME

**Unblock condition**: Feature 005 may resume only when the owner provides or authorizes a
genuine bootable SR Linux artifact whose provenance and lab use are acceptable and which can
exercise the documented SR Linux auto-boot path.

T001 tested the exact pinned SR Linux container on canonical Ubuntu x86-64 without changing
the normal Feature 004 topology or shared Compose services. The image did not enter native
DHCP/ZTP, and its chassis serial is not a usable lab identity. FR-006 therefore requires the
feature to stop. No startup configuration, bind-mounted device configuration, TFTP, alternate
DHCP option, manually started ZTP process, or container command was substituted for native
first-boot behavior.

## Canonical Environment

| Item | Observed value |
|---|---|
| Host | Ubuntu 24.04.4 LTS, kernel 6.8.0-139-generic, x86-64 |
| Docker | 29.1.3, linux/amd64 |
| containerlab | 0.79.0, commit `5ae50094a` |
| netlab | 26.08 display version for planned 26.8.0 |
| SR Linux image | `ghcr.io/nokia/srlinux:26.7.2-519` |
| SR Linux digest | `sha256:0096fe3ebcafabb7253492e2060425fe027a168e0e066766d1e85efbb0b48be8` |

The preflight found only the existing healthy `network-lab-*` supporting containers and
networks `bridge`, `host`, `none`, and `network-lab_default`. Final cleanup restored that
same set. No shared container, network, volume, topic, namespace, or normal topology was
stopped or reset.

## T001 Topologies

Three disposable raw-containerlab probes used unique `f005-t001-*` names:

1. Two `ixr-d2l` SR Linux nodes with `suppress-startup-config: true` on containerlab's
   test-owned management network, used to compare serials and restart/recreation behavior.
2. One SR Linux node with suppressed startup configuration plus one bootstrap container in
   `network-mode: none`, linked only from bootstrap `eth1` to SR Linux `ethernet-1/1`.
3. One SR Linux node and one bootstrap container both in `network-mode: none`, joined only by
   a disposable veth from bootstrap `eth1` to SR Linux `eth0` after containerlab rejected
   `eth0` as a declarative SR Linux link endpoint.

The bootstrap container published no ports, enabled no forwarding, and joined no host,
physical, Compose default, or unrelated network. dnsmasq 2.90 disabled DNS/resolver use and
reported sockets bound exclusively to `eth1`. The server address was `192.0.2.2/24`; the
test DHCP range was `192.0.2.100-192.0.2.110` and existed only on the isolated link.

## Assumption Classification

| Planned assumption | Classification | T001 evidence |
|---|---|---|
| The pinned container can enter native DHCP-discovered ZTP | **Disproven** | Fresh nodes started `/opt/srlinux/bin/sr_linux`; no `ztp`/`ztpd` process or API listener existed. `ztp service status` failed because port 50066 refused connections. |
| A complete HTTP URL in DHCP option 67 is sufficient | **Still unverified because the prerequisite failed** | dnsmasq was configured with exact value `http://192.0.2.2/ztp.py`, but neither in-band nor OOB probes emitted a DHCP Discover, so no offer or option was delivered. |
| Options 66 or 43 are unnecessary | **Still unverified** | No DHCP exchange reached option selection. Per the gate rules, no alternate option was tried. |
| Native retrieval failure and malformed-artifact behavior can be tested | **Still unverified because the prerequisite failed** | Zero HTTP requests occurred; retrieval and parsing were never reached. No artifact was modified to force a non-native path. |
| `suppress-startup-config: true` creates a genuinely blank container | **Disproven** | Each fresh node still generated an approximately 125 KiB `/etc/opt/srlinux/config.json` with container/factory management baseline. |
| The container baseline is only the planned minimum bootstrap | **Disproven** | The generated baseline included management AAA, SSH, gNMI/gNOI/gNSI/gRIBI/P4RT servers, TLS, JSON-RPC, NETCONF, SNMP, DNS, LLDP, logging, and related lab defaults before native ZTP. |
| Native ZTP can apply the proposed minimum hostname JSON | **Still unverified because the prerequisite failed** | No DHCP request, HTTP fetch, ZTP script execution, or native `configure()` call occurred. |
| Runtime-provided authentication can coexist with native minimum ZTP | **Still unverified** | Containerlab/factory baseline supplied management services, but native ZTP did not run, so this does not prove the planned bootstrap contract. |
| Chassis serial is non-empty and unique between nodes | **Disproven** | Native `/platform/chassis/serial-number` reported the same synthetic value `Sim Serial No.` on both nodes. Generated hardware details contained empty chassis and card serial fields. |
| Chassis serial is stable and suitable for `Device.serial` | **Disproven as a mapping key** | The synthetic value repeated across restart and recreation but was not unique; stability of a shared placeholder has no identity value. |
| containerlab/netlab exposes a supported deterministic serial control | **Disproven for the tested supported inputs** | No serial control was present in the tested topology type or documented containerlab SR Linux node options; image files exposed no supported serial override. No unsupported override was invented. |
| A bootstrap DHCP address can equal Nautobot `primary_ip4` | **Still unverified because DHCP never ran** | Standard containerlab assigned `172.20.20.2/.3` through Docker IPAM, not DHCP. The isolated OOB node had no IPv4 lease. |
| The planned completion predicate can be observed | **Still unverified because bootstrap and identity failed** | Lease, retrieval, native success, serial agreement, and unique mapping were absent. Containerlab-provided management alone cannot count as completion. |
| Native successful bootstrap state persists and suppresses later ZTP | **Still unverified because native bootstrap never succeeded** | No native ZTP run or artifact fetch occurred before or after restart. |
| Later running configuration survives a container restart without save | **Disproven** | A committed test hostname disappeared after restart when the startup file was not saved. |
| `containerlab save` is required for Feature 005 reboot acceptance | **Proven for later configuration on this runtime** | After `containerlab save` invoked SR Linux startup save, the same test hostname survived restart. This remains topology/test infrastructure only. |
| Destroy/recreate preserves a usable device identity | **Disproven** | The serial remained the non-unique synthetic value while per-node chassis MACs changed across recreation. No replacement identifier was selected. |

## 1. Option 67 Full-HTTP-URL Result

The configured value was exactly `http://192.0.2.2/ztp.py`. It was never delivered because
the SR Linux node emitted no DHCP packet on either tested interface. Each capture was a
24-byte empty pcap header, and each HTTP log remained zero bytes. Therefore T001 does not
show acceptance or rejection of the URL itself; it disproves the earlier prerequisite that
the pinned container starts native discovery.

## 2. Exact Native SR Linux Bootstrap Mechanism

The image contains `/opt/srlinux/bin/ztp`, `ztpd`, `ztp_dhcp_client_mgr`, `ztpclient`, and ZTP
systemd units. The container runtime does not boot systemd and started no native ZTP API or
daemon. It did run the ordinary SR Linux `sr_dhcp_client_mgr`, but that process emitted no
discovery packet in either isolated probe and is not evidence of native ZTP.

This materially differs from the physical-system R26.7 flow documented in Nokia's ZTP guide.
Manually starting the packaged service would test an injected process, not fresh native
container behavior, and was intentionally not attempted.

## 3. Minimum Bootstrap Content

No bootstrap content was requested or applied. The planned script and hostname-only JSON
were served solely as inert probe files. Their SHA-256 values were recorded during the run,
but file availability is not behavioral evidence.

The generated container baseline is materially broader than the approved minimum. T001 did
not preload loopback, routed fabric addresses, BGP ASN/neighbors, routing policy, or Feature
002 artifacts. It also cannot claim a post-bootstrap forbidden-state inspection because no
bootstrap completed.

## 4. Chassis Serial Suitability

The exact native state path tested was `/platform/chassis/serial-number`. Both nodes returned
`Sim Serial No.`. `/var/run/srlinux/devices/hw_details.json` reported empty
`chassis_serial_number` and `card_serial_number` fields. The preferred
SR Linux chassis serial -> Nautobot `Device.serial` contract is therefore unsuitable for
deterministic lab onboarding on this image.

## 5. Serial Stability Across Restart And Recreation

The synthetic serial remained unchanged through restart and recreation, but remained equal
between both nodes. This is repeatable placeholder text, not stable unique identity. Chassis
MACs differed between nodes but changed after destroy/recreate; T001 did not select them as a
fallback because the approved gate forbids selecting a replacement identifier.

## 6. Nautobot Mapping Implications

Two nodes cannot map unambiguously through core `Device.serial` when both report the same
synthetic serial. Using that value would violate FR-015 and SC-003. No Nautobot records were
created because a unique runtime identity never existed. Selecting another key requires a
new owner-approved design.

## 7. Management-Address Behavior

With normal containerlab management, Docker IPAM assigned node addresses independently of
the test DHCP service. With both containers in `network-mode: none`, the SR Linux OOB link
received no DHCP lease and retained no IPv4 address. The intended chain stable identity ->
Nautobot Device -> authoritative `primary_ip4` could not be exercised, and lease state was
not promoted into inventory.

## 8. Reliable Bootstrap-Completion Signal

No reliable completion signal exists for the tested runtime because native bootstrap never
started and no unique serial exists. The planned predicate remains logically safe but cannot
be satisfied: native success, authenticated gNMI, expected hostname, stable identifier, and
unique Nautobot mapping were not jointly observable. Containerlab-generated gNMI/AAA or an
open management path alone is not completion.

## 9. Repeated-Boot Behavior

No DHCP request or artifact fetch occurred on initial boot or restart. This is not evidence
that a successful native bootstrap disables repetition; it is evidence that the container
never entered native ZTP. Restart retained the containerlab-mounted baseline but discarded an
unsaved later running change.

## 10. Configuration Persistence

Containerlab bind-mounted `/etc/opt/srlinux` read-write. A committed running hostname was
lost after `docker restart` while the startup file remained unchanged. Repeating the change
and running `containerlab save` wrote the running configuration to
`/etc/opt/srlinux/config.json`; the hostname then survived restart.

## 11. `containerlab save`

For the accepted container runtime, `containerlab save` proved necessary for a later running
change to survive container restart. That historical result does not define redesigned
genuine-runtime acceptance. It must not become a Temporal activity, application operation,
device automation contract, or substitute for native ZTP persistence.

## 12. Architectural Consequence

Two load-bearing assumptions failed: the pinned image does not automatically execute native
DHCP/ZTP, and it does not expose a unique chassis serial. Feature 005 cannot proceed unchanged.
The stop is architectural rather than a script/config correction. A future design would need
explicit owner decisions about a supported container bootstrap mechanism and deterministic
identity, but T001 intentionally selected neither.

## 13. Genuine Boot Runtime Availability

### Decision

No genuine boot-path SR Linux runtime is selected because no practical artifact accessible to
this project could be established. Feature 005 is deferred. T003 must remain an acquisition
and provenance gate, not implementation.

### Evidence

- Nokia's public SR Linux simulator is distributed as the OCI image used by Features 001-004.
  Nokia's container installation procedure launches `/opt/srlinux/bin/sr_linux` directly;
  it is not a firmware, GRUB, storage, systemd, or factory auto-boot sequence.
- Nokia documents bootable `.bin`, SD-card, and recovery images as software-distribution
  artifacts for named physical 7215/7220/7250/7730 platforms. It does not document them as
  QEMU disks or publish a supported virtual machine definition, firmware, NIC model, or VM
  resource profile.
- The public R26.7.2-519 GitHub release has no VM asset. Public access is documented only for
  the OCI image. Nokia's support/software-delivery portal may contain entitled artifacts, but
  anonymous evidence does not establish an SR Linux VM product or this project's access to it.
- containerlab's `nokia_srlinux` kind and netlab's SR Linux support are container-only.
  netlab explicitly has no SR Linux Vagrant/libvirt provider. containerlab/vrnetlab supports
  Nokia SR OS virtual products, not SR Linux; SR OS/vSIM is excluded from this feature.
- No `.qcow2`, `.vmdk`, `.ova`, ISO, raw boot disk, QEMU/libvirt definition, or SR Linux VM
  integration exists in this repository.

Hardware-targeted SD/recovery images are not acceptable substitutes. Booting one under QEMU
without Nokia support would leave platform identity, firmware, storage, NICs, licensing, and
auto-boot applicability undefined. A generic container, startup-config mount, manually started
ZTP daemon, and SR OS/vSIM are also excluded.

### Future Artifact Gate

A candidate can be selected only when the owner supplies or authorizes access to an exact
SR Linux artifact whose provenance and permitted lab use are documented and which can be
pinned by release plus digest. Before implementation, a disposable Ubuntu x86-64 gate must
prove the actual sequence from virtual firmware/bootloader and persistent boot storage through
SR Linux auto-boot. The gate must record hypervisor/version, firmware, machine and NIC models,
vCPU/RAM/disk, acceleration, console access, image provenance/digest, licensing, interface
mapping, credential-free server-side gNMI authentication establishment, and clean teardown.
Client credentials remain runtime-only. Unknown resource requirements remain an
artifact-specific gate; the current canonical host's observed two-vCPU capacity may require resizing.

The gate must also identify authenticated post-boot state reads for disabled auto-boot and
every exact minimum configuration value. It applies one test-owned representative gNMI change
after operational startup, reboots without save, and records persistence. If the change is
lost, it repeats after native `tools system configuration save`. This determines the later
acceptance lifecycle without relying on container behavior or a snapshot.

## 14. Documented Native Mechanism

Nokia R26.7 documents this genuine flow:

```text
firmware -> GRUB/storage auto-boot flag -> ZTP service -> DHCP discovery
  -> Options 66+67, Option 67 alone, or Option 43
  -> download and execute Python provisioning script
  -> ztpclient.configure(minimum configuration)
  -> ztpclient.option_autoboot(disable)
  -> normal SR Linux operational state
```

The storage ships with auto-boot enabled. At boot SR Linux checks `grub.cfg`, starts
auto-provisioning, and tries operational OOB then supported in-band interfaces. IPv4 Option 61
defaults to chassis serial but can be configured to use chassis MAC. A valid offer includes an
infinite lease and server/address data. Options 66+67 take precedence over Option 43; Option 43
is a fallback after a 66+67 download failure. Nokia also states that Option 67 alone may carry
the complete provisioning URL, although the required-options table is less clear. Public docs
do not specify Option 43's vendor encoding, so it must not be guessed.

The Python script must check `configure()` status, then disable auto-boot only after every
minimum-bootstrap operation succeeds. A failed run releases the lease and cycles until its
configured duration/attempt bound; defaults are 3600 seconds and three attempts followed by
reboot. Console output and `/var/log/ztp` provide native evidence. Every detail, including
Option 61 contents, selected offer form, script semantics, status values, and retry timing,
must be verified on the selected runtime before becoming implementation constants.

## 15. MAC Identity And Nautobot Representation

### Decision

Use the deterministic MAC of the genuine runtime's boot management interface as the virtual
lab identity, contingent on the future runtime gate proving that the same MAC appears in DHCP
client identity/link-layer fields and remains stable across guest reboot and clean destroy/recreate.
Physical deployments may instead use a unique chassis serial; that is not the virtual
acceptance contract.

For pinned Nautobot 2.4.41, store the identity in core data only:

```text
Device
  -> directly owned Interface name=mgmt0, module=null, mgmt_only=true
  -> Interface.mac_address=AA:BB:CC:DD:EE:FF
  -> Device.primary_ip4=<deterministic DHCP management address>
```

Nautobot 2.4.41 has no standalone core MACAddress object. `Interface.mac_address` is an
optional normalized EUI-48 field, but it has no uniqueness constraint. The finite boundary
therefore canonicalizes the observed MAC to uppercase colon notation, queries
`/api/dcim/interfaces/?mac_address=<MAC>&limit=2&depth=0`, requires total count and result
length exactly one, rechecks exact MAC, then requires direct device ownership, `module=null`,
`name=mgmt0`, and `mgmt_only=true`. It follows the Device relation with existing same-origin
and ID checks and validates platform, hostname, and `primary_ip4`. The lookup must use a token
that can view every candidate Interface and Device; object permissions must not hide duplicates.

No `ztp_identity_mac` custom field is selected. It would duplicate core normalized interface
data, would not add uniqueness, and could drift. A custom field remains a fallback requiring
new owner approval only if the selected runtime cannot be modeled as a direct management
Interface.

## 16. Reboot And Persistence Redesign

The future gate must use a real guest reboot, not a container restart. It must prove that
successful native provisioning disables the boot-storage auto-boot flag, that the minimum
configuration and management access survive reboot, and that DHCP/script retrieval does not
repeat. It must also record what `configure()` persists without any lab save operation.

`containerlab save` is prohibited for the genuine-runtime acceptance path. After the existing
Feature 004 deployment succeeds, the test lifecycle may invoke SR Linux's native
`tools system configuration save` only if runtime evidence shows it is required to persist the
later intended configuration. A hypervisor snapshot is not selected and cannot substitute for
native ZTP or native configuration persistence.

## Security And Cleanup

No plaintext credential was written to probe files, packet captures, repository evidence, or
commands retained here. Evidence records only safe service status, hashes, synthetic serial,
addresses, versions, and counts; generated security configuration is not reproduced.

The test-owned SR Linux/bootstrap containers, veths, lab directories, `clab` network,
bootstrap image, captures, HTTP logs, and remote `/root/f005-t001` directory were removed.
All pre-existing `network-lab-*` services remained healthy and the final Docker network set
matched preflight.

## Sources

- [Nokia R26.7 ZTP](https://documentation.nokia.com/srlinux/26-7/books/software-install/zero-touch-provision-software-install.html)
- [Nokia R26.7 ZTP Python library](https://documentation.nokia.com/srlinux/26-7/books/software-install/appendix--ztp-python-library.html)
- [containerlab SR Linux node behavior](https://containerlab.dev/manual/kinds/srl/)
- [containerlab suppress startup config](https://containerlab.dev/manual/nodes/#suppress-startup-config)
- [dnsmasq manual](https://thekelleys.org.uk/dnsmasq/docs/dnsmasq-man.html)
- [Nokia R26.7 installing software and physical boot media](https://documentation.nokia.com/srlinux/26-7/books/software-install/install-software.html)
- [Nokia R26.7 container deployment](https://documentation.nokia.com/srlinux/26-7/books/software-install/install-containers.html)
- [Official public SR Linux container distribution](https://github.com/nokia/srlinux-container-image)
- [netlab supported platform/provider matrix](https://netlab.tools/platforms/)
- [containerlab generic VM](https://containerlab.dev/manual/kinds/generic_vm/)
- [containerlab vrnetlab support](https://containerlab.dev/manual/vrnetlab/)
- [Nautobot 2.4.41 Interface model](https://github.com/nautobot/nautobot/blob/v2.4.41/nautobot/dcim/models/device_components.py)
- [Nautobot 2.4.41 REST filtering](https://github.com/nautobot/nautobot/blob/v2.4.41/nautobot/docs/user-guide/platform-functionality/rest-api/filtering.md)
