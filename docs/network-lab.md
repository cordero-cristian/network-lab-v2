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

Attach only the existing worker with `compose.device-access.yaml`; inject credentials from
generated inventory without persisting or printing them. Remove that worker endpoint before
running `netlab down --cleanup` from `lab/`, unset both credential variables, then restore
the base worker without device credentials. See the exact commands in the Feature 004
quickstart and observed results in `docs/validation.md`. Never remove supporting Compose
volumes during topology cleanup.
