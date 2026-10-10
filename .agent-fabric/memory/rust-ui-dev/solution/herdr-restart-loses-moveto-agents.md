---
role: "rust-ui-dev"
class: solution
topic: "herdr-restart-loses-moveto-agents"
description: "What a herdr server stop/restart keeps for moveto agent tabs, measured; consequences for fabric-deck and piece 2"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: herdr
    working_copy: herdr
derived_from:
  - cd5e8fe2c0312153
---

## What a herdr server stop/restart keeps for moveto agent tabs, measured; consequences for fabric-deck and piece 2

Measured on 2026-10-07 with an isolated `herdr server` built from fork master 4cdc2765. Two tabs were made as
herd.py makes them, each running a long-lived stand-in for a moveto session. No sudo was
available, so it was not a real `sudo -u`.

**Detach or closing the terminal:** nothing is lost.

**`herdr server stop`, then start:**
- Every pane process dies.
- Workspace, tab labels and cwd come back as fresh operator shells, with no moveto and no agent.
- With `[experimental] pane_history = true` the old screen is replayed as text only. It is off by default
  because it stores secrets.
- Native agent-session resume needs the agent's herdr hook to have reported a session reference
  over the API socket. A moveto'd agent cannot: the socket is 0600 and owned by the operator, and
  `socket_access = outside_panes` would refuse it anyway. So moveto agents never resume through herdr.
- Agent status for these tabs is `unknown` even while they run.

**Consequences:**
- herd.py skips tabs whose label exists, so after a restart it leaves bare shells.
- fabric-deck (piece 3) must detect an account tab that is only an operator shell and re-run
  `moveto <account>` in it, without creating a duplicate tab.
- Piece 2's measurement should include this restart case.

See [[herdr-socket-access-design]].

*References: herdr-socket-access-design*

*Observed 2026-10-07 (rust-ui-dev)*
