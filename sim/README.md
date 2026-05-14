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

Configure the Ignition development gateway through Fluxy:

```bash
cd sim
uv run --with ../fluxy flux-sim-configure-ignition \
  field-config.sim.json \
  --base-url http://localhost:8088/system/webdev/flux \
  --tag-provider default \
  --tag-folder ACM02 \
  --opc-server "Flux Sim ACM02" \
  --batch-size 1000
```

By default, `flux-sim-configure-ignition` preserves the imported provider tree from `flux-sim.db`, including folders, UDT definitions, UDT instances, and standalone atomic OPC tags. Tree-preserving mode writes UDT definitions to the provider-level `_types_` space and writes runtime tags under `--tag-folder`. UDT instance `typeId`s are rewritten to the target provider's `_types_` path.

Use `--flat` to restore the earlier behavior that writes generated OPC tags directly under `--tag-folder`.

For a limited tree-preserving trial, merge the first 100 simulated OPC leaves and their required ancestors/types:

```bash
uv run --with ../fluxy flux-sim-configure-ignition \
  field-config.sim.json \
  --base-url http://localhost:8088/system/webdev/flux \
  --tag-provider default \
  --opc-server "Flux Sim ACM02" \
  --sim-database flux-sim.db \
  --provider ACM02 \
  --limit 100 \
  --collision-policy m
```

After a tree-preserving configure, Ignition Designer should show the original provider structure under the selected tag provider, for example:

```text
[default]_types_
[default]ACM02/WY
```

Use `--limit 100` for the first live trial if you do not want to configure the full generated tag set yet.

## Select Tags From The Django UI

Flux's Django service can browse the imported `flux-sim.db` provider tree and save simulation branch selections. This is useful when you want to choose folders or UDT instances visually instead of taking the first `--limit N` generated OPC leaves.

Start the web service and select branches at `/sim/`:

```bash
cd ../web/Flux
uv run python manage.py migrate
uv run python manage.py runserver
```

The imported provider tree UI:

- Renders folders with `📁`, UDT instances with `◆`, and standalone atomic tags with `●`.
- Uses collapsible `>` / `v` tree controls.
- Uses checkboxes for selection.
- Checking a parent recursively checks descendants.
- Shows an indeterminate checkbox when only descendants are selected.
- Hides atomic tags under UDT instances because selecting the UDT instance selects its inherited/contained OPC leaves.
- Keeps standalone atomic tags selectable.

Export selected OPC source paths:

```bash
curl 'http://localhost:8000/sim/imported/selected-paths.json?provider=ACM02' \
  > selected-paths.json
```

Configure Ignition from the selected UI paths:

```bash
cd ../../sim
uv run --with ../fluxy flux-sim-configure-ignition \
  field-config.sim.json \
  --base-url http://localhost:8088/system/webdev/flux \
  --token "$FLUXY_TOKEN" \
  --tag-provider default \
  --tag-folder ACM02 \
  --opc-server "Flux Sim ACM02" \
  --provider ACM02 \
  --sim-database flux-sim.db \
  --selected-paths-file selected-paths.json
```

## Closed Loop Trials

The preserved-tree integration test exercises the full add/read/delete/read lifecycle against live Ignition and FieldAgent:

```bash
cd sim
FLUX_SIM_IGNITION_INTEGRATION=1 \
FLUXY_TOKEN=fluxy-auth-integration-token \
uv run --with ../fluxy pytest tests/test_integration_preserved_tree_ignition.py
```

The test:

- Deletes stale `[default]ACM02` runtime tags.
- Configures a limited preserved provider tree.
- Reads `[default]ACM02/WY/AL/PADS/AL01-16/AL01-16_RTU_35/METER/Meter_Gas_Sales_01/OPC/PRESSURE_DIFF` until it is `Good`.
- Deletes `[default]ACM02`.
- Reads the same path again and confirms it is gone.

During configure, source-provider `tagGroup` values are stripped for simulation trials because custom production tag groups such as `Tubing_Casing` may not exist on a dev gateway.

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
- Django is not required for the command-line flow, but it now provides provider tree selection controls that export `selected_source_paths` for `flux-sim-configure-ignition`.
