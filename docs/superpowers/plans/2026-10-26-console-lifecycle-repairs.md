# Console and message lifecycle repairs Implementation Plan

> **For agentic workers:** Use executing-plans inline, with a final fresh review. The user's four-part work order is the binding spec; do not pause for plan approval or alter production.

**Goal:** Preserve reading state on timed refresh, consolidate Bot startup, recover evidenced legacy scenes/identities, and retain outbound message provenance.

**Architecture:** Keep runtime scopes, permissions and context isolation intact. Derive read-only legacy projections per record, carry immutable outbound provenance, and commit refreshed DOM as one transaction with reading anchors.

**Tech Stack:** Existing Python unittest, Node test runner, local Edge/Playwright, pwsh and Windows PowerShell 5.1; no dependency installation.

**Spec:** User work order dated 2026-10-26 (four parts); acceptance baseline is `docs/reviews/2026-10-26-user-identity-triage-acceptance.md`.

## Global Constraints

- Work in existing dev, baseline `0568dac`; no production changes, QQ, migration, new push, PR or main merge.
- Obtain four failures before production edits; synthetic temporary data and finite substitute processes only.
- Keep original review conclusions; distinguish fresh evidence from historical 233/47/43 results.
- Manual confirmation, unlink and denial override automatic evidence; display aggregation never grants operational authority.
- No nickname, text, time, last route or shared profile key as identity evidence.

## Review Focus

- Scrolling or editing while a refresh is awaiting responses must supersede the earlier snapshot.
- Mixed legacy files with conflicting or missing row evidence must remain partitioned and explainable.
- Identity evidence lost on a later event must not erase earlier proof; conflicts and denials persist.
- Late accepted callbacks and duplicate receipt persistence must retain the original target and request.
- Startup failure must preserve the actual child exit code without interpreter retry.

### Task 1: Four reproductions

- [x] Add real timer browser assertions for reading anchors using a temporary Console instance.
- [x] Add dual-shell child-exit and entry inventory regressions in launcher tests; run against baseline.
- [x] Add legacy record-level source/identity projection failures to Node and Python tests.
- [x] Add outbound delayed provenance, duplicate history and self-event failures using real extracted methods.
- [x] Record actual failures and root causes in the review ledger before implementation.

### Task 2: Reading preservation

Files: `console/public/index.html`, `console/public/user-workbench.js`, new reading-state helper, browser regression.

- [x] Stage refresh requests; retain live DOM until all selected scene data is ready, preserve current selection/expansion/focus and semantic anchors at commit time.
- [x] Cover window and independent scrollers, insert/delete/reorder, two real timer rounds at middle/bottom, in-flight scrolling, narrow viewport and editing/dialog protections.

### Task 3: One startup entry

Files: `scripts/start-bot.cmd`, `scripts/start-bot.ps1`, existing duplicate cmd files, Console caller, launcher tests and startup documentation.

- [x] Keep only `scripts/start-bot.cmd`; remove two developer-repo wrappers, update callers and current instructions, retain historical records with a dated supersession note.
- [x] Keep shell selection before execution; propagate component exit codes and bounded identity establishment without weakening nonce/PID/exe/ticks checks.
- [x] Execute isolated matrices under both shells and both selection paths, quoted paths, foreign cwd, concurrency and all existing failures.

### Task 4: Legacy evidence and identity

Files: `console/people-sources.js`, `console/user-workbench.js`, workbench UI, `user_profiles.py`, identity/legacy regressions.

- [x] Resolve row source before file scope; derive separate synthetic read-only scene origins where necessary, keep unknown/conflicted rows visible and preserve raw files.
- [x] Accept only historical full source or reproducible validated scope hashes; bare original sender keys cannot distinguish private/group.
- [x] Retain validated app identity proof across sparse later observations, surface scoped conflicts, and keep artificial read-only origins out of management targets.
- [x] Regress manual decisions, stale revisions, history/memory/points/permission boundaries and document evidence gaps by class.

### Task 5: Outbound provenance

Files: `main.py`, `session_scope.py`, `qq_delivery.py`, `task_runtime.py` as needed, Console history projection and synthetic Python/Node/browser tests.

- [x] Bind outbound receipts to target, triggering immutable source and request/job before awaits; use explicit triggers for proactive/admin sends, no invented original task.
- [x] Preserve assistant role; accepted history idempotence, failed/unknown receipts remain inspectable; reject platform self-message events before writing scopes or starting work.
- [x] Correct group projection to verify outbound destination and applicable request/job, including no-original-task messages, without assigning a group announcement to a recent speaker.
- [x] Cover parallel groups/private targets, delayed callback, duplicate receipts, media/segments and process-restart readback; no automatic resend/replay on restart.

### Task 6: Delivery

- [x] Run fresh affected/full offline suites and real browser regressions, inspect synthetic screenshots; log commands and uncovered platform branches.
- [x] Update MODIFICATIONS, DEVELOPMENT, review, TASKS and handoff with deployment/obsolete-entry cleanup and rollback.
- [x] Review staged diff and secrets, fix blocking findings, make local commit(s) only and deliver hashes with separate review/acceptance/push/deploy/QQ states.
