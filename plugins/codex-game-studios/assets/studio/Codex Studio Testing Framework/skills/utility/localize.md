# Skill Test Spec: $localize

## Codex Runtime Contract

- Runtime skill: `.agents/skills/localize/SKILL.md`
- Runtime name: `localize`
- Runtime trigger description: `"Use when game strings, translations, cultural review, VO, RTL support, string freeze, or localization QA need attention."`
- Native invocation: `$localize`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$localize` is tested against the exact runtime discovery contract above. The five
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
- [ ] Contains verdict keywords: LOCALIZATION COMPLETE, GAPS FOUND
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff (e.g., send locale skeletons to translators)

---

## Director Gate Checks

None. `$localize` is a pipeline utility. No director gates apply. Localization
lead agent may review separately but is not invoked within this skill.

---

## Test Cases

### Case 1: New Language — String Extraction and Locale Skeleton Created

**Fixture:**
- Source code in `src/` contains player-facing strings (UI text, tutorial messages)
- Existing locale: `assets/localization/en.csv`
- No French locale exists

**Input:** `$localize fr`

**Expected behavior:**
1. Skill extracts all player-facing strings from source files
2. Skill finds the same strings in `en.csv` as a reference
3. Skill generates `fr.csv` skeleton with all string keys and empty values
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
5. File written on approval; verdict is GAPS FOUND (file created but empty values)
6. Skill notes: "fr.csv created — send to translator to fill values"

**Assertions:**
- [ ] All string keys from `en.csv` are present in `fr.csv`
- [ ] All values in `fr.csv` are empty (not copied from English)
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is GAPS FOUND (file is created but untranslated)

---

### Case 2: Existing Locale Diff — Additions, Removals, and Changes Listed

**Fixture:**
- `assets/localization/fr.csv` exists with 20 string keys translated
- Source code has changed: 3 new strings added, 1 string removed, 2 strings
  with changed English source text

**Input:** `$localize fr`

**Expected behavior:**
1. Skill extracts current strings from source
2. Skill diffs against existing `fr.csv`
3. Skill produces diff report:
   - 3 new keys (need translation — listed as empty in fr.csv)
   - 1 removed key (marked as obsolete — suggest removal)
   - 2 changed keys (English source changed — French may need update, flagged)
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
5. File updated with new empty keys added, obsolete keys marked; verdict is GAPS FOUND

**Assertions:**
- [ ] New keys appear as empty in the updated file (not auto-translated)
- [ ] Removed keys are flagged as obsolete (not silently deleted)
- [ ] Changed source strings are flagged for translator review
- [ ] Verdict is GAPS FOUND (new empty keys exist)

---

### Case 3: String Missing in One Locale — GAPS FOUND With Missing Key List

**Fixture:**
- 3 locale files exist: `en.csv`, `fr.csv`, `de.csv`
- `de.csv` is missing 4 keys that exist in both `en.csv` and `fr.csv`

**Input:** `$localize`

**Expected behavior:**
1. Skill reads all 3 locale files and cross-references keys
2. `de.csv` is missing 4 keys
3. Skill produces GAPS FOUND report listing the 4 missing keys by locale:
   "de.csv missing: [key1], [key2], [key3], [key4]"
4. Skill offers to add the missing keys as empty values to `de.csv`
5. After approval: file updated; verdict remains GAPS FOUND (values still empty)

**Assertions:**
- [ ] Missing keys are listed explicitly (not just a count)
- [ ] Missing keys are attributed to the specific locale file
- [ ] Verdict is GAPS FOUND (not LOCALIZATION COMPLETE)
- [ ] Missing keys are added as empty (not auto-translated from English)

---

### Case 4: Translation File Has Syntax Error — Error With Line Reference

**Fixture:**
- `assets/localization/fr.csv` has a malformed line at line 47
  (missing quote closure)

**Input:** `$localize fr`

**Expected behavior:**
1. Skill reads `fr.csv` and encounters a parse error at line 47
2. Skill outputs: "Parse error in fr.csv at line 47: [error detail]"
3. Skill cannot diff or validate the file until the error is fixed
4. Skill does NOT attempt to overwrite or auto-fix the malformed file
5. Skill suggests fixing the file manually and re-running `$localize`

**Assertions:**
- [ ] Error message includes line number (line 47)
- [ ] Error detail describes the nature of the parse error
- [ ] Skill does NOT overwrite or modify the malformed file
- [ ] Manual fix + re-run is suggested as remediation

---

### Case 5: Director Gate Check — No gate; localization is a pipeline utility

**Fixture:**
- Source code with player-facing strings

**Input:** `$localize fr`

**Expected behavior:**
1. Skill extracts strings and manages locale files
2. No director agents are spawned
3. No gate IDs appear in output

**Assertions:**
- [ ] No director gate is invoked
- [ ] No gate skip messages appear
- [ ] Verdict is LOCALIZATION COMPLETE or GAPS FOUND — no gate verdict

---

## Protocol Compliance

- [ ] Extracts strings from source before operating on locale files
- [ ] Creates new locale files with all keys as empty values (not auto-translated)
- [ ] Diffs existing locale files against current source strings
- [ ] Flags missing keys by locale and by key name
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is LOCALIZATION COMPLETE (all locales fully translated) or GAPS FOUND

---

## Coverage Notes

- LOCALIZATION COMPLETE is only achievable when all locale files have all keys
  with non-empty values; new-language skeleton creation always results in GAPS FOUND.
- Engine-specific locale formats (Godot `.translation`, Unity `.po` files) are
  handled by the skill body; `.csv` is used as the canonical format in tests.
- The case where source strings change at a very high rate (continuous integration
  of new UI text) is not tested; the diff logic handles this case.
