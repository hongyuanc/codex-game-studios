# Networking Instructions

## Applies To

All files below `src/networking/`.

## Required Practices

- Keep the server authoritative for all gameplay-critical state and validate all incoming packet sizes and field ranges.
- Version every network message for forward and backward compatibility.
- Use local client prediction, server reconciliation, and rollback for mispredictions.
- Handle disconnection, reconnection, and host migration gracefully.
- Rate-limit network logging.
- Document each value's reliable or unreliable replication mode, frequency, interpolation, and per-message-type bandwidth budget.

## Forbidden Practices

- Do not trust client-provided gameplay-critical state.
- Do not introduce unversioned messages or unbounded packet fields, logs, or bandwidth.
- Do not add prediction without a reconciliation and rollback path.

## Verification

Run compatibility, packet validation, disconnect/reconnect, host-migration, prediction/rollback, and bandwidth-budget tests under adverse network conditions.
