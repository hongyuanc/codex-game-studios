# Skill Test Spec: $security-audit

## Codex Runtime Contract

- Runtime skill: `.agents/skills/security-audit/SKILL.md`
- Runtime name: `security-audit`
- Runtime trigger description: `"Use when game code or data flows need a diagnostic security review before release or multiplayer exposure."`
- Native invocation: `$security-audit`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$security-audit` is tested against the exact runtime discovery contract above. The five
cases below preserve its domain fixtures, expected outputs, verdict vocabulary, review
modes, and edge conditions.

Validation is read-only. If the workflow writes, the parent first presents one
complete proposed changeset containing every target path and material edit; any
new path or scope expansion requires fresh approval. If it delegates, direct
children return scoped evidence and the parent synthesizes the result.

---

## Static Assertions (Structural)

Verified automatically by `$skill-test static` — no fixture needed.

- [ ] Runtime YAML frontmatter has only the required discovery fields `name` and `description`, and both match the contract above
- [ ] Has ≥2 phase headings
- [ ] Contains verdict keywords: SECURE, CONCERNS, VULNERABILITIES FOUND
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff (what to do with findings)

---

## Director Gate Checks

None. Security audit is a read-only advisory skill; no gates are invoked.

---

## Test Cases

### Case 1: Happy Path — Save data encrypted, no hardcoded credentials

**Fixture:**
- `src/core/save_system.gd` uses `Crypto` class to encrypt save data before writing
- No hardcoded API keys, passwords, or credentials in any `src/` file
- No version numbers or internal build IDs exposed in client-facing output

**Input:** `$security-audit`

**Expected behavior:**
1. Skill scans `src/` for security patterns: encryption usage, hardcoded credentials, exposed internals
2. All checks pass: save data encrypted, no credentials found, no exposed internals
3. Findings report shows all checks PASS
4. Verdict is SECURE

**Assertions:**
- [ ] Skill checks save data handling for encryption usage
- [ ] Skill scans for hardcoded credentials (API keys, passwords, tokens)
- [ ] Skill checks for version/build numbers exposed to players
- [ ] All checks shown in findings report
- [ ] Verdict is SECURE when all checks pass

---

### Case 2: Vulnerabilities Found — Unencrypted save data and exposed version

**Fixture:**
- `src/core/save_system.gd` writes save data as plain JSON (no encryption)
- `src/ui/debug_overlay.gd` contains: `label.text = "Build: " + ProjectSettings.get("application/config/version")`
  (exposes internal build version to player)

**Input:** `$security-audit`

**Expected behavior:**
1. Skill scans `src/` — finds unencrypted save write in `save_system.gd`
2. Skill finds exposed version string in `debug_overlay.gd`
3. Both findings are flagged as VULNERABILITIES
4. Verdict is VULNERABILITIES FOUND
5. Skill provides remediation recommendations for each vulnerability

**Assertions:**
- [ ] Unencrypted save data is flagged as a vulnerability with file and approximate line
- [ ] Exposed version string is flagged as a vulnerability
- [ ] Remediation suggestion is given for each vulnerability
- [ ] Verdict is VULNERABILITIES FOUND when any vulnerability is detected
- [ ] No files are written or modified

---

### Case 3: Online Features Without Authentication — CONCERNS

**Fixture:**
- `src/networking/lobby.gd` exists with functions: `join_lobby()`, `send_chat()`
- No authentication check is found before `send_chat()` — players can call it without being verified
- Game has online multiplayer features (inferred from file presence)

**Input:** `$security-audit`

**Expected behavior:**
1. Skill scans `src/networking/` — detects online feature code
2. Skill checks for authentication guard before network calls — finds none on `send_chat()`
3. Flags: "Online feature without authentication check — CONCERNS"
4. Verdict is CONCERNS (not VULNERABILITIES FOUND, as this is a missing control, not an exploit)

**Assertions:**
- [ ] Skill detects online features by scanning for networking source files
- [ ] Missing authentication checks before network operations are flagged
- [ ] Verdict is CONCERNS (advisory severity) for missing authentication guards
- [ ] Output recommends adding authentication before network calls

---

### Case 4: Edge Case — No Source Files to Analyze

**Fixture:**
- `src/` directory does not exist or is completely empty

**Input:** `$security-audit`

**Expected behavior:**
1. Skill attempts to scan `src/` — no files found
2. Skill outputs an error: "No source files found in `src/` — nothing to audit"
3. No findings report is generated
4. No verdict is emitted

**Assertions:**
- [ ] Skill does not crash when `src/` is empty or absent
- [ ] Output clearly states that no source files were found
- [ ] No verdict is emitted (there is nothing to assess)
- [ ] Skill suggests verifying the `src/` directory path

---

### Case 5: Gate Compliance — No gate; security-engineer invoked separately

**Fixture:**
- Source files exist; 1 CONCERNS-level finding detected (debug logging enabled in release build)
- `.codex/studio.toml` contains `full`

**Input:** `$security-audit`

**Expected behavior:**
1. Skill scans source; finds debug logging active in release path
2. No director gate is invoked regardless of review mode
3. Verdict is CONCERNS
4. Output notes: "For formal security review, consider engaging a security-engineer agent"
5. Findings are presented as a read-only report; no files written

**Assertions:**
- [ ] No director gate is invoked in any review mode
- [ ] Security-engineer consultation is suggested (not mandated)
- [ ] No files are written
- [ ] Verdict is CONCERNS for advisory-level security findings

---

## Protocol Compliance

- [ ] Reads source files in `src/` before auditing
- [ ] Checks save data encryption, hardcoded credentials, exposed internals, auth guards
- [ ] Provides remediation recommendations for each finding
- [ ] Does not write any files (read-only skill)
- [ ] No director gates are invoked
- [ ] Verdict is one of: SECURE, CONCERNS, VULNERABILITIES FOUND

---

## Coverage Notes

- Anti-cheat analysis (client-side value validation, server authority) is not
  explicitly tested here; it follows the CONCERNS or VULNERABILITIES pattern
  depending on severity.
- Data privacy compliance (GDPR, COPPA) is out of scope for this spec; those
  require legal review beyond code scanning.
