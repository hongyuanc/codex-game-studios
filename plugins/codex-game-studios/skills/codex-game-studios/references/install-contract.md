# Installation contract

All manager planning and `verify` calls are read-only. They must not create a
lock, installation-state directory, or any other target-repository content.
Every mutating operation (`install`, `update`, `repair`, or `uninstall`) requires
an explicit approval bound to the exact plan digest returned for the current
plugin payload and observed repository state.

Present the entire plan before asking for approval, including creates, adopts,
updates, merges, removals, backups, preserved paths, and conflicts. Never pass a
digest from another plan or synthesize one. The manager reacquires and checks
the plan while holding its cooperative lock; a changed repository produces a
stale-plan error and requires a new plan and new approval.

The manager may write only beneath the resolved Git root after approval. It
must validate the embedded payload, reject unsafe paths and links, preserve a
same-filesystem recovery snapshot, apply the action list, validate the result,
and record state before reporting success. Project operations make no network
requests and collect no credentials or telemetry.
