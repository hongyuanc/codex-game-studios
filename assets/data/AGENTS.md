# Data File Instructions

## Applies To

All files below `assets/data/`.

## Required Practices

- Keep every JSON file valid JSON and name files in lowercase with underscores using `[system]_[name].json`.
- Document every data schema in JSON Schema or the corresponding design document.
- Explain numeric values in companion documentation and use camelCase JSON keys consistently.
- Ensure every entry is referenced by code or another data file.
- Version breaking schema changes and give all optional fields sensible defaults.

## Forbidden Practices

- Do not commit invalid JSON, uppercase or space-separated filenames, undocumented schemas, orphaned entries, or unexplained numeric values.
- Do not make a breaking schema change without versioning it.

## Verification

Parse every changed JSON file, validate its filename and schema, scan for orphaned references, and exercise defaults and schema-version migrations.
