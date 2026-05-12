# dev_tag_builder

Carl's workspace for offline Ignition tag-building trials.

## Inputs

- `../instance_exports.sqlite3`
- The expansion query joins `tag_dataset_rows` to `equipment` by `subtype_id`.

Requested query shape:

```sql
select concat('"', tag_path, '/', tag_name,'",')
from tag_dataset_rows
join equipment on tag_dataset_rows.subtype_id = equipment.subtype_id
```

SQLite equivalent used by the tooling:

```sql
select equipment.tag_path || '/' || tag_dataset_rows.tag_name as tag_path
from tag_dataset_rows
join equipment on tag_dataset_rows.subtype_id = equipment.subtype_id
```

## Build

```bash
python build_memory_tags.py
```

Outputs are written to `out/`:

- `providers.txt`: tag providers to create in Ignition before import/configure.
- `tag_paths.txt`: unique generated full tag paths.
- `import_Tag_02.json`: Ignition provider-root JSON import for `Tag_02`.
- `import_Tag_03.json`: Ignition provider-root JSON import for `Tag_03`.
- `import_Tag_04.json`: Ignition provider-root JSON import for `Tag_04`.
- `manifest.json`: maps providers to generated import files.

## Current Findings

Current provider requirements from `instance_exports.sqlite3`:

- `Tag_02`
- `Tag_03`
- `Tag_04`

Current unique tag count is expected to be `35,220`.

## Import Shape

Carl reviewed `tags.json` and now emits the same provider-root shape:

```json
{
  "name": "",
  "tagType": "Provider",
  "tags": []
}
```

Leaf tags are memory Float tags:

```json
{
  "dataType": "Float4",
  "defaultValue": 1,
  "name": "LOAD_FACTOR",
  "tagType": "AtomicTag",
  "value": 1,
  "valueSource": "memory"
}
```

## Need From More Sample Tag Exports

When the sample tag export is available, check:

- Whether Ignition export JSON prefers `dataType: Float4` or another exact type string.
- Whether `tagType: AtomicTag` plus `valueSource: memory` matches the target version.
- Whether imports preserve provider names or require provider-stripped relative paths.
- Whether folder creation should be explicit or implicit.
