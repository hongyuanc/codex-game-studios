# Recovery after rollback failure

`ROLLBACK_FAILED` means the manager could not verify byte-for-byte restoration.
Do not rerun a mutation, delete the manager lock path, edit the journal, or
remove the recovery snapshot. The retained snapshot and journal may be the only
known-good recovery material.

1. Stop all repository writes, including IDE formatters and Git operations.
2. Preserve the complete JSON error response. Record the operation, affected
   relative paths, write status, and reported journal state without exposing
   file contents or machine-specific absolute paths in public logs.
3. Back up the repository and the retained recovery directory as-is.
4. Escalate for project-owner review of the journal and snapshot before any
   manual restoration.
5. After an authorized recovery, run the read-only `verify` operation. Do not
   resume mutation until verification and recovery-state checks succeed.

Never claim that rollback or recovery succeeded until the manager or an
authorized recovery procedure verifies the restored bytes.
