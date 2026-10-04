# Optional SR Linux Topology

Feature 004 provides a separately managed two-node SR Linux topology for deployment and
operational validation. It remains outside supporting-service health and lifecycle.

Use an Ubuntu 24.04 LTS x86-64 host for the reference path. Install a jointly
tested release of [netlab](https://netlab.tools/install/) and
[containerlab](https://containerlab.dev/install/), ensure the user can access the
Docker daemon, and obtain the Nokia SR Linux image required by the selected
containerlab release. An x86 virtual host must expose SSSE3. Budget device memory
in addition to the 16 GiB supporting-service budget.

Tested deployment tuple on Ubuntu 24.04.4 LTS x86-64 on 2026-09-11:
netlab/networklab 26.08, containerlab 0.79.0, and Nokia SR Linux 26.7.2-519.
The SR Linux image supplied a native amd64 manifest and was pulled successfully.

SR Linux multi-architecture images exist from 24.10.1, but upstream describes
ARM64 as preview. containerlab requires Linux networking primitives. Docker Desktop
on macOS is therefore not the reference network-device host even when the Compose
supporting services work there. No amd64 emulation is forced by this repository.

From `lab/`, start exactly the Feature 004 topology without applying generated intent:

```sh
netlab up topology.yml -p clab --no-config
netlab status
```

Running from `lab/` confines generated `clab-*`, inventory, and configuration files to
ignored paths and prevents cleanup from colliding with the repository's root `config/`.
The topology owns only management/gNMI access, one link, and hostname identity bootstrap.
Nautobot and automation own all loopback, routed-interface, and BGP intent.

Attach only the existing worker and, when the read-only Feature 006 UI is enabled, its API
with `compose.device-access.yaml`; inject credentials from generated inventory without
persisting or printing them. The UI API uses this attachment only for one on-demand device
detail read. Its 15-second operation budget is not a polling interval: overview, inventory,
topology, and subsequent device-detail refreshes do not contact devices.

With the accepted topology already running and credentials exported only in the current
shell, start the API attachment and same-origin UI proxy with:

```sh
docker compose \
  -f compose.yaml \
  -f compose.device-access.yaml \
  --profile ui \
  up -d automation-ui-api automation-ui
```

No UI/API route renders, deploys, retries, remediates, publishes, changes Nautobot, sends a
gNMI Set, or otherwise mutates the lab. Device access failure degrades only live detail;
inventory and retained Temporal evidence remain observable. Diagnose independently with
`curl --fail http://127.0.0.1:8001/healthz`, API/UI container logs, and the source status
shown in the UI. API liveness deliberately does not probe Nautobot, Kafka, Temporal, or a
device.

Before `netlab down --cleanup`, stop both optional UI services and the override worker,
unset both credential variables, then restore the base worker without device credentials:

```sh
docker compose -f compose.yaml -f compose.device-access.yaml --profile ui stop automation-ui automation-ui-api
unset LAB_DEVICE_USERNAME LAB_DEVICE_PASSWORD
```

Run cleanup from `lab/`. See the exact worker restoration commands in the Feature 004
quickstart and observed results in `docs/validation.md`. Never remove supporting Compose
volumes during topology or UI cleanup.
