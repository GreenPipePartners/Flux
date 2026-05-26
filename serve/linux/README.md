# Flux Linux Service Wrapper

Linux deployments use native systemd units. On Arch, RHEL, Rocky, and Alma, systemd is the expected service manager.

Initial model:

```text
flux-web.service
flux-worker.service
```

The Linux path runs Python directly under systemd. Cross-platform service wrappers are intentionally out of scope.

Install the web project dependencies before enabling `flux-web.service`:

```bash
cd web/Flux
uv sync
```
