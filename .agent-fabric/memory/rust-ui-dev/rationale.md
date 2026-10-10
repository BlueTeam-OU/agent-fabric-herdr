---
role: "rust-ui-dev"
class: rationale
description: "Why herdr's socket switch filters callers instead of unbinding, how a peer is placed inside a pane, and what it means for fabric-deck"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: herdr
    working_copy: herdr
derived_from:
  - 34040c0af8f3406b
---

## Why herdr's socket switch filters callers instead of unbinding, how a peer is placed inside a pane, and what it means for fabric-deck

Piece 1 of the herdr request (gzapi-org/herdr#3) adds `[server] socket_access` = all | outside_panes | client_only.

Why it is shaped this way (2026-10-07):
- **"Off" cannot unbind the API socket.** The TUI pings it before attaching to a running server,
  and `herdr server stop`, `herdr update` and live handoff all use it. So `ping` is always
  answered, and client_only still serves stop, live_handoff and ssh_agent.register.
- **The client socket is a second control path** (endpoint methods, `terminal attach`/`control`),
  so both sockets are gated.
- **"Inside a pane" means a session leader whose start-time /proc environ has `HERDR_ENV=1`
  without `HERDR_POPUP=1`.** That leader is the peer, its session leader or an ancestor; or the
  peer kept the marker after its leader exited. "Descendant of the server" fails after a live
  handoff, where pane shells are reparented to init.
- **Popups carry `HERDR_POPUP`.** They are the person's own configured commands; panes strip any
  inherited marker.
- **A reload re-judges open connections.** Each connection registers with the gate before it is
  judged, and a reload that tightens the mode shuts the socket of every one it now refuses
  (unix only).
- **Linux only for placement.** macOS and Windows place every peer "unidentified", so the
  restricted modes refuse everything there but ping.
- **Not a boundary between processes of one account.** A process that clears its environment
  and then leaves the session or outlives its pane escapes; running an agent as another login is
  the real isolation.

**Consequence for piece 3 (fabric-deck):** herd.py drives the API from wherever it is run. Under
outside_panes the deck must be launched from the operator's own terminal, outside any pane, and
attach the client afterwards; its fabric-ctl states listener then runs outside panes too.

See [[herdr-host-toolchain]].

*References: herdr-host-toolchain*

*Observed 2026-10-07 (rust-ui-dev)*
