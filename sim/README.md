# Flux Sim

Standalone simulation core for reconstructing Ignition tag providers and preparing OPC UA simulation artifacts.

## Put A Provider Online

This path brings a simulated provider online through FieldAgent and a live Ignition development gateway.

Prerequisites:

- A running Ignition development gateway with Fluxy WebDev deployed.
- `FLUXY_BASE_URL` pointed at that gateway, usually `http://localhost:8088/system/webdev/flux`.
- `FLUXY_TOKEN` if the WebDev bridge requires one.
- .NET SDK available for `field/Flux.FieldAgent`.
- `fluxy` available to `/sim`, easiest with `uv run --with ../fluxy ...`.

Prepare the standalone sim DB and FieldAgent config:

```bash
cd sim
uv run --with ../fluxy flux-sim-prepare-online \
  ../tags02.json \
  --provider ACM02 \
  --database flux-sim.db \
  --field-config field-config.sim.json \
  --endpoint-url opc.tcp://localhost:4840/flux/sim \
  --namespace-uri urn:flux:sim:acm02
```

Start FieldAgent with the generated config:

```bash
cd ..
dotnet run \
  --project field/Flux.FieldAgent/Flux.FieldAgent.csproj \
  --FluxField:ConfigPath=/home/bobby/Projects/11006-PRW-flux/sim/field-config.sim.json \
  --FluxField:CertificateStorePath=/tmp/flux-sim-pki
```

Run the functional smoke against Ignition:

```bash
cd sim
FLUX_SIM_IGNITION_INTEGRATION=1 \
FLUXY_BASE_URL=http://localhost:8088/system/webdev/flux \
FLUX_SIM_FIELD_ENDPOINT_URL=opc.tcp://localhost:4840/flux/sim \
FLUX_SIM_OPC_SERVER="Flux Sim ACM02" \
uv run --with ../fluxy pytest tests/test_integration_sim_to_ignition.py
```

The smoke test creates a small Ignition-side folder, configures OPC tags that point at FieldAgent, reads values, confirms they change, then cleans up.

## Notes

- Do not use `--skip-raw-config` for provider reconstruction. UDT OPC bindings live in raw Ignition config payloads.
- Full `tags02.json` currently expands to a large FieldAgent config. Use the functional smoke first before attempting the full ACM02 provider in Ignition.
- Django is not required for this flow. Django should only expose UX/configurator controls over these steps.
