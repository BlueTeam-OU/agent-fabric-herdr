---
role: "rust-ui-dev"
class: index
description: "What rust-ui-dev knows and where it lives."
tier: 1
distilled_at: "2026-10-10"
---

# rust-ui-dev — knowledge index

A session is given the charter and brief (in the launch prompt),
and the project's remit with a pointer to this index (from the
session-start hook) — nothing below. Open a slice when its cue
matches what you are doing; a `workflow` slice says how a kind of
work is done here, so read the matching ones before that work.
Paths are relative to this working copy; `../agent-fabric/` is the
control plane checked out beside it.

## charter

- [`../agent-fabric/identities/roles/rust-ui-dev/charter.md`](../agent-fabric/identities/roles/rust-ui-dev/charter.md) — The fleet's native-client developer in Rust: the user interface on Slint across desktop and mobile, its accessibility, the client's local store and its privacy posture, and the acceptance tests a person's use of it must pass.

## brief

- [`../agent-fabric/identities/roles/rust-ui-dev/brief.md`](../agent-fabric/identities/roles/rust-ui-dev/brief.md) — How rust-ui-dev works day to day, in any project: a change begins from the person's journey, is designed as well as built, rests on agreed contracts, and is verified in the rendered client on every platform before it is called done.

## domain

- [`../agent-fabric/memory/domains/rust-ui-dev/domain/atspi-e2e-lessons.md`](../agent-fabric/memory/domains/rust-ui-dev/domain/atspi-e2e-lessons.md) — Driving a Slint/AccessKit window over AT-SPI in tests -- what the adapter answers, focus under Xvfb, hearing announcements, SELinux on this host
- [`../agent-fabric/memory/domains/rust-ui-dev/domain/slint-rendered-window-lessons.md`](../agent-fabric/memory/domains/rust-ui-dev/domain/slint-rendered-window-lessons.md) — Slint 1.18 layout/font traps the testing backend does not show -- monospace by name, wrap min-width, a component's height from its only child layout; look at the winit window under Xvfb

## solution

- [`.agent-fabric/memory/rust-ui-dev/solution/herdr-agent-row-display.md`](.agent-fabric/memory/rust-ui-dev/solution/herdr-agent-row-display.md) — what a person actually reads in herdr's agent sidebar for a reported pane, and the report-metadata rules that bite
- [`.agent-fabric/memory/rust-ui-dev/solution/herdr-host-toolchain.md`](.agent-fabric/memory/rust-ui-dev/solution/herdr-host-toolchain.md) — What building and checking the herdr fork needs on develop-qzapp beyond cargo, and which test failures are host artefacts
- [`.agent-fabric/memory/rust-ui-dev/solution/herdr-pane-focus-reporting.md`](.agent-fabric/memory/rust-ui-dev/solution/herdr-pane-focus-reporting.md) — What a herdr pane learns about its own focus (DECSET 1004): changes only, never the state at enable; and why a focused plugin tab did not move clients
- [`.agent-fabric/memory/rust-ui-dev/solution/herdr-restart-loses-moveto-agents.md`](.agent-fabric/memory/rust-ui-dev/solution/herdr-restart-loses-moveto-agents.md) — What a herdr server stop/restart keeps for moveto agent tabs, measured; consequences for fabric-deck and piece 2
- [`.agent-fabric/memory/rust-ui-dev/solution/herdr-restore-drops-plugin-panes.md`](.agent-fabric/memory/rust-ui-dev/solution/herdr-restore-drops-plugin-panes.md) — A herdr session restore keeps a plugin tab's label but runs a shell in place of the plugin's program; judge a tab by its process, not its label
- [`.agent-fabric/memory/rust-ui-dev/solution/herdr-sound-paths.md`](.agent-fabric/memory/rust-ui-dev/solution/herdr-sound-paths.md) — Where herdr decides and plays agent sounds (server vs client, shell vs attach), and how the fork's per-transition sounds hook in
- [`.agent-fabric/memory/rust-ui-dev/solution/moveto-sudo-own-pty.md`](.agent-fabric/memory/rust-ui-dev/solution/moveto-sudo-own-pty.md) — why herdr process-info on a moveto pane never shows claude — sudo use_pty puts the account on its own pty

## rationale

- [`.agent-fabric/memory/rust-ui-dev/rationale.md`](.agent-fabric/memory/rust-ui-dev/rationale.md) — Why herdr's socket switch filters callers instead of unbinding, how a peer is placed inside a pane, and what it means for fabric-deck

## workflow

- [`.agent-fabric/memory/rust-ui-dev/workflow.md`](.agent-fabric/memory/rust-ui-dev/workflow.md) — Codex was removed from gzapi-org on 2026-10-09: never wait for a Codex review; still check for unresolved threads before calling the gate met

## recall

- [`../agent-fabric/identities/roles/rust-ui-dev/recall.md`](../agent-fabric/identities/roles/rust-ui-dev/recall.md) — Where rust-ui-dev's knowledge lives — charter, remit, distilled slices, this agent's memory — and how to trace a claim to its sources.
