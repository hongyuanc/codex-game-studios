# Security Policy

## Supported versions

Only the `main` branch receives security fixes. Forks and older releases are not
supported.

## Report a vulnerability

Do not open a public issue. Use
[GitHub private vulnerability reporting](https://github.com/Donchitos/Codex-Code-Game-Studios/security/advisories/new)
and include reproduction steps, impact, affected files, and mitigations.

We aim to acknowledge reports within 48 hours, provide a status update within
seven days, and resolve confirmed issues within 90 days.

## In scope

Codex Game Studios runs local project instructions, skills, custom agents, and
Python hook actions. Relevant vulnerabilities include:

- malicious or undisclosed behavior in `.codex/hooks/hook_runner.py`;
- command parsing that permits destructive Git operations without approval;
- skills or profiles that expose secrets or make undisclosed network requests;
- prompt injection that bypasses phase gates or expands file scope;
- unsafe path handling, symlink traversal, or platform-specific validation gaps;
- model routing that silently substitutes non-OpenAI services or ignores the
  configured Sol/Terra/Luna GPT policy;
- unaudited changes to `.codex/hooks.json`, `.codex/agents/*.toml`, or
  `.codex/studio.toml`.

Issues in Codex itself, the OpenAI API, or an OpenAI account should be reported
through [OpenAI security](https://openai.com/security/). Game-project defects,
theoretical attacks without a plausible path, and physical-access attacks are
out of scope for this repository.

## Contributor security rules

- Keep hook actions in Python 3 and add tests for safe and unsafe inputs.
- Do not read credentials unless a documented, user-approved workflow requires
  the specific value.
- Do not add silent network calls or telemetry.
- Keep changes within an approved phase boundary. Commits, pushes, releases,
  destructive actions, and external publication remain separately gated.
- Use repository-relative paths and validate links, JSON, TOML, and user input.
- Document model-routing changes and keep all runtime providers OpenAI/Codex.

## Disclosure

We use coordinated disclosure: private report, acknowledgement, assessment,
tested fix, reporter notification, then publication after the fix ships or at
90 days. Reporters are credited unless they request anonymity.
