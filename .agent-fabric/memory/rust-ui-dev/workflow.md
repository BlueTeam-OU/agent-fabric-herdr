---
role: "rust-ui-dev"
class: workflow
description: "Codex was removed from gzapi-org on 2026-10-09: never wait for a Codex review; still check for unresolved threads before calling the gate met"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: herdr
    working_copy: herdr
derived_from:
  - 9619fad96469af07
---

## Codex was removed from gzapi-org on 2026-10-09: never wait for a Codex review; still check for unresolved threads before calling the gate met

The owner uninstalled the ChatGPT Codex Connector from gzapi-org at about 07:50Z on 2026-10-09 (gh api orgs/gzapi-org/installations: total_count 0; fabric-coordinator broadcast 01a11fb2-7531). No new Codex review or thread will appear on a fork PR. The review class's blind review of the head is the review (agent-fabric ADR-020).

Before that date the bot posted inline P1/P2 threads. On herdr#7 (2026-10-08), three of them, one a P1, sat unseen through four blind-review rounds.

**Why:** an unresolved thread still blocks the arm gate, whoever wrote it.

**How to apply:** do not hold a PR waiting for Codex. Before calling the gate met, check that pr-gate.sh shows threads=0. A leftover Codex thread is judged on its merits, then answered and resolved with pr-reply.sh. See [[herdr-host-toolchain]].

*References: herdr-host-toolchain*

*Observed 2026-10-09 (rust-ui-dev)*
