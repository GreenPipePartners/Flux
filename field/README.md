# Flux Field

Flux Field is the OPC UA simulation server project. It is intentionally separate from the Django web app and from service-wrapper infrastructure.

Boundary:

```text
field/
- C# OPC UA simulation server runtime
- .NET Worker Service implementation
- Windows Service and systemd compatible executable

web/Flux/src/flux/sim/
- Django simulation selection/configuration UI
- `/sim/field-config.json` for the FieldAgent

web/Flux/src/flux/serve/
- worker/process status and supervision UX

web/Flux/field/
- Flux Field config workspace and notes
```

The first runtime target is `field/Flux.FieldAgent`, a .NET 10 worker using the OPC Foundation UA stack.

Run the server from an exported Flux config file:

```bash
dotnet run --project field/Flux.FieldAgent/Flux.FieldAgent.csproj --FluxField:ConfigPath=/home/bobby/Projects/11006-PRW-flux/web/Flux/field/field-config.json
```

Default endpoint:

```text
opc.tcp://localhost:4840/flux/field
```

Default seeded nodes:

```text
ns=2;s=FluxLogix001.BoolTag
ns=2;s=FluxLogix001.IntegerTag
ns=2;s=FluxLogix001.FloatTag
```

## Simulation Model

Flux Field is configured from Flux through `/sim/field-config.json`. The source of truth is the integrated Flux database, usually Postgres in deployed environments. Django admin edits the table configuration, and FieldAgent treats that configuration as a device factory.

Relationship model:

```text
FieldEndpoint
  has many FieldDevice
    has many FieldTag
```

This is intentionally many-to-one from tags to devices: one simulated device owns many tag definitions. FieldAgent reads the exported endpoint config and spawns each configured device plus all enabled tags under that device.

Each simulated tag has:

- `name`
- `data_type`: `bool`, `int`, `float`, or `string`
- `update_rate_ms`
- `simulation_type`: `toggle`, `ramp`, `wave`, `random_walk`, or `static`
- `min_value`
- `max_value`
- `variance`
- `initial_value`

The default seeded device is `FluxLogix001`, intended to mimic a small ControlLogix-style device namespace. Additional ControlLogix-style devices should be added as `FieldDevice` rows, not hard-coded in the agent or tests.

## Integration Test Contract

The Django-side integration test is gated because it requires a live Ignition gateway and a running Flux Field OPC UA server:

```bash
FLUX_FIELD_INTEGRATION=1 uv run pytest -m integration src/flux/field/test_integration_field.py
```

Useful environment variables:

- `FLUXY_BASE_URL`: Fluxy WebDev base URL.
- `FLUXY_PROJECT_LOCATION`: Ignition project location for WebDev deployment.
- `FLUX_FIELD_ENDPOINT_URL`: Flux Field OPC endpoint URL.
- `FLUX_FIELD_OPC_SERVER`: Ignition OPC server name used by configured tags.
- `FLUX_FIELD_TAG_PROVIDER`: Ignition tag provider, default `default`.

The test flow is:

1. Build simulated Flux Field endpoint/device/tag rows.
2. Export those rows into FieldAgent config.
3. Use Fluxy to configure an Ignition OPC UA connection.
4. Use Fluxy to add Ignition OPC tags pointing at FieldAgent nodes.
5. Read successful qualified values.
6. Sample repeatedly and assert values change.
7. Delete the tags.

Current implementation status:

- The FieldAgent starts a real OPC UA server.
- The server creates device folders and variable nodes from Flux config.
- Bool, int, float, and string values are generated from configured simulation settings.
- Values update at each tag's `update_rate_ms`.
- Anonymous/no-security OPC UA access is enabled for the first local integration pass.
