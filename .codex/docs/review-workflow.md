# Review Workflow

This studio uses phase-gated autonomy:

1. The user approves concepts, material design and architecture decisions,
   scope changes, milestone changes, and each implementation story changeset.
2. After story approval, the implementing agent may edit the agreed files, add
   tests, and iterate until the acceptance criteria pass.
3. Code changes receive review from the relevant department lead; design and
   architecture changes receive their appropriate director review.
4. Cross-domain changes are coordinated by `producer` and pause if they expand
   beyond the approved boundary.
5. Commits, pushes, releases, publication, and destructive actions require
   separate explicit authorization.
