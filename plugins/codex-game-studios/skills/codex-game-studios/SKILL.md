---
name: codex-game-studios
description: Install, update, verify, repair, or uninstall the Codex Game Studios operational framework in a Git repository through a plan-first, digest-bound manager protocol.
---

# Codex Game Studios Manager

Manage the repository studio only through this skill. The supported operation
set is exactly `install|update|verify|repair|uninstall`. Reject any other
operation rather than forwarding it to the manager.

Before running the manager, read [references/install-contract.md](references/install-contract.md).
When the plan reports a collision or customization, apply
[references/conflict-policy.md](references/conflict-policy.md). If the manager
reports `ROLLBACK_FAILED`, stop and follow
[references/recovery.md](references/recovery.md).

## Protocol

1. Resolve `<plugin-root>` as this installed plugin's root and `<git-root>` as
   the target repository root. Keep both paths explicit and correctly quoted.
2. Map the user's requested operation to one member of the supported operation
   set. Run the read-only planning command exactly once:

   ```text
   python3 <plugin-root>/scripts/studio_manager.py <operation> --root <git-root> --format json
   ```

3. Parse the JSON response. Present its full action list, conflicts, preserved
   paths, warnings, and validation findings without omission or rewriting.
   If the complete response exceeds the conversation transport limit, save the
   exact unmodified JSON outside the target repository as a Codex artifact,
   link that artifact, and present its action counts and digest. Do not apply
   until the user can access that complete artifact and explicitly approves it.
   Exit `2` with `status: awaiting-approval` is the expected successful planning
   result for a mutation. Exit `0` is a completed success; exit `1` is a stable
   categorized failure.
4. For `verify`, display every ordered relative-path entry in `findings`
   exactly once and stop. Do not omit, summarize, or replace findings with the
   status or conflict list. `verify` runs once, remains
   read-only, and never requests approval.
5. For `install`, `update`, `repair`, or `uninstall`, request explicit approval
   for the displayed plan. Do not treat general intent, earlier approval, or
   approval of another digest as approval for this plan.
6. Only after approval, copy the exact digest and opaque `approval_context`
   returned by the planning response into the apply command:

   ```text
   python3 <plugin-root>/scripts/studio_manager.py <operation> --root <git-root> --approve-digest <digest> --approval-context <context> --format json
   ```

   Always use both exact returned values: never invent, shorten, normalize,
   decode, recalculate, or otherwise alter the digest or approval context.
7. Present the complete JSON result. Never claim success when the manager
   reports an error or incomplete rollback. Route `ROLLBACK_FAILED` directly to
   `references/recovery.md` and preserve every relative path and phase in its
   trusted `recovery` object. Never synthesize missing recovery metadata.

Every JSON response contains `status`, `operation`, `digest`, `actions`,
`conflicts`, `findings`, `wrote`, `recovery`, `next_action`,
`approval_context`, and `failure_phase`. Treat `wrote` and `recovery` as
authoritative; never infer write or rollback status from the presence of target
files. `failure_phase` is null on success and otherwise names only a stable,
content-free manager phase; never replace it with guessed exception details.

The manager commands are the only authorized interface. Do not reproduce their
filesystem mutations manually or enable embedded project hooks as plugin
lifecycle hooks.
