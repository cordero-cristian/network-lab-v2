# Optional SR Linux Topology

Feature 001 provides only a minimal topology input. It does not launch, configure,
or validate a network device and is not part of supporting-service health.

Use an Ubuntu 24.04 LTS x86-64 host for the reference path. Install a jointly
tested release of [netlab](https://netlab.tools/install/) and
[containerlab](https://containerlab.dev/install/), ensure the user can access the
Docker daemon, and obtain the Nokia SR Linux image required by the selected
containerlab release. An x86 virtual host must expose SSSE3. Budget device memory
in addition to the 16 GiB supporting-service budget.

Candidate tuple selected from current releases on 2026-09-08: netlab/networklab
26.8, containerlab 0.79.0, and Nokia SR Linux 26.7.2-519. The repository has not
executed this tuple; verify it together on the reference Linux host before treating
it as tested or changing the topology to depend on release-specific behavior.

SR Linux multi-architecture images exist from 24.10.1, but upstream describes
ARM64 as preview. containerlab requires Linux networking primitives. Docker Desktop
on macOS is therefore not the reference network-device host even when the Compose
supporting services work there. No amd64 emulation is forced by this repository.

From `lab/`, validate and generate provider artifacts without starting a node:

```sh
netlab create topology.yml -p clab
```

Generated `clab-*`, inventory, and configuration files are ignored. Remove them
with the version-appropriate netlab cleanup command. `netlab up` and device access
are deliberately deferred to later features.

The exact netlab/containerlab/SR Linux tuple still requires validation on the
reference Linux host; see `docs/validation.md`.
