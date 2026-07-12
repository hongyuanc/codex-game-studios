# Conflict policy

The manager preserves project-owned and customized content. Never bypass a
reported conflict or manually force the planned mutation.

- An unowned, non-identical target is an `UNMANAGED_COLLISION`; preserve it and
  resolve ownership before planning again.
- A managed target that differs from its recorded hash is a
  `CUSTOMIZED_MANAGED_FILE`; preserve the customization and reconcile it before
  retrying.
- Malformed or contradictory managed blocks stop the operation for explicit
  project-owner resolution.
- Game-owned paths and unrelated Codex configuration remain untouched.
- Uninstall removes only content whose current hash or managed block still
  proves manager ownership. Customized remnants and their required legal notice
  stay in place and are reported.

After resolving a conflict, discard the old digest and run a new read-only plan.
Approval never carries across plans.
