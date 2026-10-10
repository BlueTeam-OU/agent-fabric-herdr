//! Fork: the server's side of `crate::transition_sound`.

use super::*;
use crate::detect::{Agent, AgentState};
use crate::transition_sound::{choose, pane_account, Choice, Label};

impl HeadlessServer {
    fn pane_account(&self, pane_id: crate::layout::PaneId) -> Option<String> {
        let (_, pane) = self.app.find_pane(pane_id)?;
        let terminal = self.app.state.terminals.get(&pane.attached_terminal_id)?;
        pane_account(&terminal.metadata_tokens.values())
    }

    fn transition_sound_choice_for(
        &self,
        account: Option<&str>,
        from: AgentState,
        to: AgentState,
        agent: Option<Agent>,
    ) -> Choice {
        if !self.app.state.sound.allows(agent) {
            return Choice::Unset;
        }
        choose(&self.app.state.sound, account, from, to)
    }

    /// Whether the transition tables replace the sound upstream would send
    /// for this transition; its callers then send none.
    pub(super) fn transition_sound_claims(
        &self,
        pane_id: crate::layout::PaneId,
        from: AgentState,
        to: AgentState,
        agent: Option<Agent>,
    ) -> bool {
        let account = self.pane_account(pane_id);
        self.transition_sound_choice_for(account.as_deref(), from, to, agent)
            .claims()
    }

    /// Sends a configured transition sound to the clients, at most once a
    /// second per pane. Returns `transition_sound_claims` for the transition.
    pub(super) fn play_transition_sound(
        &mut self,
        pane_id: crate::layout::PaneId,
        from: AgentState,
        to: AgentState,
        agent: Option<Agent>,
    ) -> bool {
        let account = self.pane_account(pane_id);
        let choice = self.transition_sound_choice_for(account.as_deref(), from, to, agent);
        if matches!(choice, Choice::Play(_))
            && self.transition_sound_limiter.allow(
                pane_id,
                Instant::now(),
                Duration::from_millis(self.app.state.sound.fleet_min_interval_ms),
            )
        {
            let label = Label {
                from,
                to,
                account,
                fallback: crate::app::actions::notification_sound_for_state_change(false, from, to),
            };
            self.send_transition_sound(label.encode());
        }
        choice.claims()
    }

    /// Every shell client plays it, as each plays upstream's semantic
    /// sounds; a shell client without the fork ignores it. Only shell
    /// clients hear transition sounds: the foreground client is always a
    /// shell (the handshake and every promotion name one), so no
    /// terminal-attach client is ever sent one (review F2).
    fn send_transition_sound(&mut self, label: String) {
        self.send_to_client_shells(ServerMessage::Notify {
            kind: protocol::NotifyKind::Sound,
            message: label,
            body: None,
        });
    }
}
