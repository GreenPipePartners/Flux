# Flux Field Configuration

This directory is the project-level configuration workspace for Flux Field.

The active Django app lives at:

```text
web/Flux/src/flux/field/
```

That location is required for the Python namespace `flux.field`.

The FieldAgent reads exported configuration from Flux through:

```text
/field/config.json
```

The config supports multiple simulated devices. Each device exposes configured tags with a tag name, data type, update rate in milliseconds, min/max values, variance, and simulation type.

The Django model relationship is:

```text
FieldEndpoint
  has many FieldDevice
    has many FieldTag
```

In deployed Flux, these rows should live in the integrated Postgres database. Django admin is the first-class configuration UI for this device factory.

You can export the same payload to a file with:

```bash
uv run python manage.py export_field_config --output field/field-config.json
```
