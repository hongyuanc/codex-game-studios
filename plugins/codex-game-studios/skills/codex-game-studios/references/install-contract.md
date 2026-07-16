# Installation contract

All manager planning and `verify` calls are read-only. They must not create a
lock, installation-state directory, or any other target-repository content.
Every mutating operation (`install`, `update`, `repair`, or `uninstall`) requires
an explicit approval bound to the exact plan digest returned for the current
plugin payload and observed repository state.

The planning response also returns an opaque, shell-safe `approval_context`.
It binds the planned transaction UUID and RFC3339 UTC installation timestamp
to the exact state bytes and plan digest. Pass it back unchanged together with
`--approve-digest`; never decode, edit, reuse, or synthesize it. Missing,
malformed, operation-mismatched, tampered, or replayed context fails closed.

The read-only mutation plan exits `2` to distinguish “awaiting explicit
approval” from a completed operation. This is not an error. A conflict or
manager failure exits `1`; a completed apply or clean verify exits `0`.

Present the entire plan before asking for approval, including creates, adopts,
updates, merges, removals, backups, preserved paths, and conflicts. Never pass a
digest from another plan or synthesize one. The manager reacquires and checks
the plan while holding its cooperative lock; a changed repository produces a
stale-plan error and requires a new plan and new approval.

When the complete canonical response is too large for the conversation
transport, store that exact response as a Codex artifact outside the target
repository and provide a link, action counts, and digest. The artifact is the
complete plan presented for approval; a truncated message is not.

For `verify`, present every canonical ordered relative-path object in the
`findings` array without omission. An empty array is the exact clean result;
never infer findings from status, actions, or conflicts.

The manager may write only beneath the resolved Git root after approval. It
must validate the embedded payload, reject unsafe paths and links, preserve a
same-filesystem recovery snapshot, apply the action list, validate the result,
and record state before reporting success. Project operations make no network
requests and collect no credentials or telemetry.

Approved apply uses a private verified snapshot of the exact digest-bound
payload so a concurrent marketplace cache refresh cannot change bytes during a
transaction. Error JSON reports only a fixed-vocabulary `failure_phase`; it
must not expose filesystem paths, payload content, or exception text.
