---
role: "rust-ui-dev"
class: solution
topic: "herdr-sound-paths"
description: "Where herdr decides and plays agent sounds (server vs client, shell vs attach), and how the fork's per-transition sounds hook in"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: herdr
    working_copy: herdr
derived_from:
  - 02d6c10159a0d90e
---

## Where herdr decides and plays agent sounds (server vs client, shell vs attach), and how the fork's per-transition sounds hook in

herdr's server decides sounds; the client plays them with its own config. Three paths:
- **Shell clients** (plain `herdr`): `SemanticNotification.sound` from
  `forward_semantic_agent_transition` (src/server/headless/notifications.rs), only for
  -> blocked (request) and -> idle after work (done); the client shell drops a done sound
  for the focused active tab. Shell clients ignore `ServerMessage::Notify`.
- **Attach clients** (`herdr attach`): `Notify { kind: Sound, message: "agent done" |
  "agent attention" }` to the foreground client, from the StateChanged / HookStateReported
  arms and `forward_pane_state_update_notifications_to_clients`; delayed toasts
  (`delay_seconds` > 0) go through `forward_agent_notification_delivery` instead.
- API-driven transitions (deck's report-agent) reach `forward_semantic_agent_transition`
  from headless.rs's API path; an idle with no `last_agent_completion_seq` is skipped there.

The fork's per-transition sounds (j47, branch feat/transition-sounds, 2026-10-10) decide in
`play_transition_sound` at the top of `forward_semantic_agent_transition`, send a label
("transition idle->working fallback=none account=<login>") as Notify to shell clients, and
clear upstream's sound where a table claims the transition. The account is the pane metadata
token `account`. Limits: one per pane per second, and `[ui.sound] fleet_min_interval_ms`
(default 250, 0 off) across panes; both apply to table-chosen sounds only. Not covered: the delayed attach-client path.

Server tests that drive report-agent must drain internal events and use an EndpointControl
barrier before reading the client channel: `try_recv` alone was flaky (3 of 5 failing).

*Observed 2026-10-09 (rust-ui-dev)*
