# Flux Serve

Flux Serve contains platform-native service wrapper assets for the Flux on-prem service suite.

- `windows/Flux.Agent/`: .NET Worker Service wrapper for Windows Service deployments.
- `linux/systemd/`: systemd unit templates for Linux deployments.

Flux Field's OPC UA server runtime lives at repository-level `field/`, not under `serve/`. `serve/` only contains platform service wrappers/templates.

The Django-side service management app lives in `web/Flux/src/flux/serve/` and owns service heartbeats, approved command rows, and the operator-facing HTMX views.

Initial runtime boundary:

```text
Windows Service or systemd
  -> Flux worker
      -> flux.opt scheduler
      -> fluxy Ignition API calls
      -> Flux database cache
```
