# Flux Linux Service Wrapper

Linux deployments use native systemd units. On Arch, RHEL, Rocky, and Alma, systemd is the expected service manager.

Initial model:

```text
flux-web.service
flux-worker.service
```

The Linux path can run Python directly under systemd first. A cross-platform `.NET Flux.Agent` can be added later only if product symmetry is worth the extra moving part.

Install the Linux web dependency group before enabling `flux-web.service`:

```bash
uv sync --group linux
```
