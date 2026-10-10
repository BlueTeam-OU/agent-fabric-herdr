---
role: "rust-ui-dev"
class: solution
topic: "herdr-pane-focus-reporting"
description: "What a herdr pane learns about its own focus (DECSET 1004): changes only, never the state at enable; and why a focused plugin tab did not move clients"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: herdr
    working_copy: herdr
derived_from:
  - ce87ca6a0fdfbfb8
---

## What a herdr pane learns about its own focus (DECSET 1004): changes only, never the state at enable; and why a focused plugin tab did not move clients

Measured live on develop-qzapp, 2026-10-09, while building the fleet views (fleet-deck/fabric_view.py):

- **herdr forwards focus *changes* only** to a pane that set DECSET 1004 (pane/tab switch, outer
  terminal focus; `src/app/api.rs` sync_focus_events). A pane is never told its state when it turns
  1004 on. A pane created focused (`plugin pane open --focus`) is focused *before* its program
  enables 1004, so it gets no focus-in; a pane opened in a background tab never gets a focus-out.
  A view that assumes "focused at open" polls in the background. Fix used: focus unknown until a
  focus-in or a key, and the opening action passes `--env FABRIC_VIEW_OPENED_FOCUSED=1`.
- **Attached clients keep their own tab surface** (`src/server/headless/client_views.rs`). After a
  public create they follow the server only via `public_create_requests_focus`; upstream lists
  only workspace.create and tab.create, so `plugin pane open --placement tab --focus` focused the
  server's tab while the client kept drawing the old one. The fork adds plugin.pane.open (focus,
  or zoomed): commit 3ed20ab8 on develop-qzapp/rust-ui-dev-01/feat/fleet-views. Upstream herdrdev/herdr
  has the bug.
- **Testing herdr live under a scratch XDG_CONFIG_HOME/XDG_STATE_HOME leaks into the panes**: gh
  finds no login (pr-gate fails) and fabric-jobs reads an empty store. Read results with that in
  mind, or pass the real dirs to the panes.

See [[herdr-socket-access-design]], [[herdr-host-toolchain]].

*References: herdr-host-toolchain, herdr-socket-access-design*

*Observed 2026-10-09 (rust-ui-dev)*
