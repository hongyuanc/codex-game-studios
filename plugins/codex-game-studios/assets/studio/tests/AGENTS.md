# Test Instructions

## Applies To

All files below `tests/`.

## Required Practices

- Name tests with the `test_[system]_[scenario]_[expected_result]` pattern.
- Give every test an explicit arrange, act, and assert structure.
- Keep unit tests independent of external filesystem, network, database, or shared mutable state; use dedicated immutable fixtures where needed.
- Make integration tests clean up after themselves.
- Give performance tests explicit thresholds that fail when exceeded.
- Mock external dependencies so tests stay fast and deterministic.
- Add a regression test for every bug fix that would have caught the original defect.

## Forbidden Practices

- Do not rely on external or shared mutable state in unit tests.
- Do not use vague names, imprecise assertions, or performance tests without thresholds.
- Do not fix a bug without its regression test.

## Verification

Run the focused suite and complete regression suite, repeat deterministic tests, verify integration cleanup, and inspect each bug fix for its regression test.
