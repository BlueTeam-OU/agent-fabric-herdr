---
role: "rust-ui-dev"
class: solution
topic: "herdr-restore-drops-plugin-panes"
description: "A herdr session restore keeps a plugin tab's label but runs a shell in place of the plugin's program; judge a tab by its process, not its label"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: herdr
    working_copy: herdr
derived_from:
  - fb5ef3d99f9ff757
---

## A herdr session restore keeps a plugin tab's label but runs a shell in place of the plugin's program; judge a tab by its process, not its label

Measured on a real herdr server (this fork's debug build, session r2, 2026-10-10): after `server stop` and re-attach,
a tab opened by `plugin pane open` (placement tab) and renamed `fleet` comes back with its label and a bare
operator shell in its pane; the plugin's program is not restarted, and `pane list` has no plugin field.
So fabric-deck judges the fleet tab by `pane process-info` (the board's argv: `-c` code importing fabric_view,
last arg `board`); a lone bare shell is its remnant, closed and reopened; anything else is a person's.
A plugin pane's own program leads its process group, so `shell_pid == foreground_process_group_id`
alone mistakes a running view for a bare shell: check the foreground argv is a shell too.
Fixed in BlueTeam-OU/agent-fabric-herdr#10 (fleet-deck/fabric_deck.py `_fleet_tab_holds`).

Rendered checks: debug herdr keeps its own config (~/.config/herdr-dev); set `onboarding = false` there or the
onboarding overlay eats the view's keys. A pty client read back with pyte needs `report_device_status`
overridden (pyte 0.8.2 rejects herdr's private DSR). See [[herdr-host-toolchain]], [[herdr-restart-loses-moveto-agents]].

*References: herdr-host-toolchain, herdr-restart-loses-moveto-agents*

*Observed 2026-10-09 (rust-ui-dev)*
