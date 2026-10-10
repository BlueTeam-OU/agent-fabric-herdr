---
role: "rust-ui-dev"
class: solution
topic: "herdr-agent-row-display"
description: "what a person actually reads in herdr's agent sidebar for a reported pane, and the report-metadata rules that bite"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: herdr
    working_copy: herdr
derived_from:
  - f87674326fcbb0a6
---

## what a person actually reads in herdr's agent sidebar for a reported pane, and the report-metadata rules that bite

Measured live on the fork (2f98e063) with a herdr client in xterm on a private Xvfb, 2026-10-08, for gzapi-org/herdr#7:

- **The default agent row shows no state word.** `[ui.sidebar.agents] rows` defaults to `["state_icon", "machine", "workspace", "tab"], ["agent"]` (docs/next/.../configuration.mdx). `--state-label STATUS=TEXT` only shows through a `state_text` token. To make a word visible with no config, set it with `report-metadata --display-agent <word>`, and `--clear-display-agent` to get herdr's own name back.
- **report-metadata refuses a clear and a set of the same field in one call:** "cannot set and clear the same metadata field". Send `--clear-state-labels` and the new `--state-label` as two calls.
- **herdr shows an unseen `idle` as `done`.** A label meant for idle must also be set as `done=<word>`.
- **`pane split --ratio 0.65` leaves 65 % to the original pane.** `split` has no `--label`; use `pane rename <pane> <label>`. The root pane keeps focus.

How the rendered check was run: `Xvfb :87`, `xterm -e herdr` against an isolated `HERDR_SOCKET_PATH`, then `import -window root`. See [[herdr-host-toolchain]] and [[moveto-sudo-own-pty]].

*References: herdr-host-toolchain, moveto-sudo-own-pty*

*Observed 2026-10-08 (rust-ui-dev)*
