# Audited safety repair plan

Baseline: dd87d03a67268ab5c79e92805fab6e9709453433. Python 3.12.3 audit: 60 tests passed, 2 failed; Ruff 18 findings; mypy 45 errors in 8 files. Source-review risks are not live API reproductions. No repairs are claimed complete by this document.

## Issue map

YT-001 #3 occurrence identity; YT-002 #2 deletion IDs; YT-003 #1 self-merge; YT-004 #6 destination consistency; YT-005 #4 source retention; YT-006 #5 deletion recovery; YT-007 #7 ordering; YT-008 #9 scan reconciliation; YT-009 #8 availability uncertainty; YT-010 #10 public MCP discovery; YT-011 #12 transports; YT-012 #11 dry-run defaults; YT-013 #14 inventory coverage; YT-014 #15 Ruff; YT-015 #13 typing; YT-016 #16 reproducibility; YT-017 #17 canonical references.

## Phase 1: lossless inventory

Capture failing regressions, then implement occurrence-level remote IDs and positions. Add backed-up, versioned migrations; legacy IDs remain unresolved until rescanned. Stage scan generations and reconcile only completed scopes, retaining history. Track failure/checkpoints and distinguish occurrence counts from unique video counts. Missing details remain uncertain, never automatic deletion evidence. Add migration, pagination, partial-failure and rescan tests beyond the initial regressions.

Gate: synthetic scan/export/rescan is lossless; partial scans never prune valid prior data.

## Phase 2: mutation safety

Default all layers to dry-run; reject self-merge and unresolved IDs before writes. Preserve ordering. Merge becomes plan/copy/verify, retaining source by default. Persist returned destination item IDs and per-step journal; handle retries and partial success. Separate source deletion approval. Remote deletion failure preserves local inventory. Private-to-public copying requires explicit approval.

Gate: mocked failure-injection and call-order tests pass; no real playlist mutations.

## Phase 3: compatibility and quality

Use public MCP discovery. Configure transports through supported SDK settings and test bounded local startup/discovery/shutdown. Fix lint and strict typing without global suppressions or blanket unsafe autofixes. Align canonical repository references.

Gate: tests, Ruff and mypy pass; no public endpoint exposed.

## Phase 4: reproducibility

Record dependencies and commands; independently run Python 3.11/3.12/3.13 tests, lint and types with artifacts. Validate Nix separately. Verify documented integration flags exist.

## Phase 5: separately approved live pilot

Use read-only OAuth and bounded scans first. Preserve snapshots and original titles/order/privacy. Export complete catalogue before classification and rename proposals. Cross-playlist overlap is not inherently unwanted duplication. No source deletion until exact reviewed approval and verification.

## Change controls

Work only on the repair branch. No direct main writes, automatic merges, credential transfers, public deployments or live playlist changes. Issues remain open until their acceptance criteria are tested; report partial progress honestly.
