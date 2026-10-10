//! Fork: transition sounds through the server, as Fleet Deck drives a pane.

use super::*;
use api::schema::PaneAgentState;

const ACCOUNT: &str = "rust-ui-dev-01";

struct Deck {
    server: HeadlessServer,
    control_rx: std::sync::mpsc::Receiver<Vec<u8>>,
    pane: String,
}

impl Deck {
    fn new(sound: &str) -> Self {
        let (writer, control_rx, _render_rx) = test_client_writer();
        let (mut server, pane_id) = completion_guard_server(writer);
        server.app.state.sound = toml::from_str::<crate::config::Config>(sound)
            .unwrap()
            .ui
            .sound;
        let pane = server.app.public_pane_id(0, pane_id).unwrap();
        let mut deck = Self {
            server,
            control_rx,
            pane,
        };
        completion_guard_api_report(
            &mut deck.server,
            api::schema::Method::PaneReportMetadata(api::schema::PaneReportMetadataParams {
                pane_id: deck.pane.clone(),
                source: "fabric".into(),
                agent: Some("claude".into()),
                applies_to_source: None,
                title: None,
                display_agent: None,
                state_labels: Default::default(),
                tokens: HashMap::from([(
                    crate::transition_sound::ACCOUNT_TOKEN.into(),
                    Some(ACCOUNT.into()),
                )]),
                clear_title: false,
                clear_display_agent: false,
                clear_state_labels: false,
                seq: None,
                ttl_ms: None,
            }),
        );
        deck
    }

    fn report(&mut self, state: PaneAgentState) {
        let pane = self.pane.clone();
        self.report_on(pane, state);
    }

    /// The pane in the second workspace, which has no account token.
    fn other_pane(&self) -> String {
        let pane_id = self.server.app.state.workspaces[1].tabs[0].root_pane;
        self.server.app.public_pane_id(1, pane_id).unwrap()
    }

    fn report_on(&mut self, pane: String, state: PaneAgentState) {
        completion_guard_api_report(
            &mut self.server,
            api::schema::Method::PaneReportAgent(api::schema::PaneReportAgentParams {
                pane_id: pane,
                source: "fabric".into(),
                agent: "claude".into(),
                state,
                message: None,
                seq: None,
                agent_session_id: None,
                agent_session_path: None,
                resume_argv: None,
            }),
        );
    }

    /// The sound labels and semantic sounds the client was sent since the last call.
    fn sent(
        &mut self,
    ) -> (
        Vec<String>,
        Vec<Option<protocol::SemanticNotificationSound>>,
    ) {
        let mut labels = Vec::new();
        let mut semantic = Vec::new();
        self.server.drain_all_internal_events_with_forwarding();
        self.server.send_to_client(
            1,
            ServerMessage::EndpointControl {
                kind: "test.transition-barrier".into(),
                data: String::new(),
            },
        );
        loop {
            let bytes = self
                .control_rx
                .recv_timeout(Duration::from_secs(1))
                .expect("transition barrier");
            match read_server_message(bytes) {
                ServerMessage::EndpointControl { kind, .. }
                    if kind == "test.transition-barrier" =>
                {
                    break
                }
                ServerMessage::Notify {
                    kind: protocol::NotifyKind::Sound,
                    message,
                    ..
                } => labels.push(message),
                ServerMessage::SemanticNotification(notification) => {
                    semantic.push(notification.sound)
                }
                _ => {}
            }
        }
        (labels, semantic)
    }
}

#[test]
fn a_configured_account_transition_sends_its_label_to_shell_clients() {
    let mut deck = Deck::new(
        r#"
[ui.sound.accounts."rust-ui-dev-01"]
"idle -> working" = "sounds/working.mp3"
"#,
    );
    deck.report(PaneAgentState::Idle);
    let _ = deck.sent();
    deck.report(PaneAgentState::Working);
    assert_eq!(
        deck.sent().0,
        ["transition idle->working fallback=none account=rust-ui-dev-01"]
    );
}

#[test]
fn an_off_transition_drops_upstreams_sound_but_keeps_the_notification() {
    let mut deck = Deck::new("[ui.sound.transitions]\n\"* -> blocked\" = \"off\"\n");
    deck.report(PaneAgentState::Working);
    let _ = deck.sent();
    deck.report(PaneAgentState::Blocked);
    let (labels, semantic) = deck.sent();
    assert!(labels.is_empty());
    assert_eq!(
        semantic,
        [None],
        "the needs-attention notice still goes out, silent"
    );
}

#[test]
fn a_claimed_transition_replaces_upstreams_sound_rather_than_adding_to_it() {
    let mut deck = Deck::new("[ui.sound.transitions]\n\"working -> blocked\" = \"b.mp3\"\n");
    deck.report(PaneAgentState::Working);
    let _ = deck.sent();
    deck.report(PaneAgentState::Blocked);
    let (labels, semantic) = deck.sent();
    assert_eq!(
        labels,
        ["transition working->blocked fallback=request account=rust-ui-dev-01"]
    );
    assert_eq!(semantic, [None]);
}

#[test]
fn with_empty_tables_the_server_sends_what_upstream_sends() {
    let mut deck = Deck::new("[ui.sound]\nenabled = true\n");
    deck.report(PaneAgentState::Idle);
    deck.report(PaneAgentState::Working);
    let _ = deck.sent();
    deck.report(PaneAgentState::Blocked);
    let (labels, semantic) = deck.sent();
    assert!(labels.is_empty());
    assert_eq!(
        semantic,
        [Some(protocol::SemanticNotificationSound::Request)]
    );
}

#[test]
fn an_unknown_pane_reported_idle_plays_its_configured_sound() {
    // A pane the deck held as unknown goes back to idle over the socket
    // API: no completion, so upstream notifies nothing, and the
    // configured transition still sounds (review F1).
    let mut deck = Deck::new("[ui.sound.transitions]\n\"unknown -> idle\" = \"back.mp3\"\n");
    deck.report(PaneAgentState::Unknown);
    let _ = deck.sent();
    deck.report(PaneAgentState::Idle);
    assert_eq!(
        deck.sent().0,
        ["transition unknown->idle fallback=none account=rust-ui-dev-01"]
    );
}

#[test]
fn a_pane_passing_several_transitions_at_once_sounds_once() {
    let mut deck = Deck::new("[ui.sound.transitions]\n\"* -> *\" = \"any.mp3\"\n");
    deck.report(PaneAgentState::Idle);
    deck.report(PaneAgentState::Working);
    deck.report(PaneAgentState::Blocked);
    deck.report(PaneAgentState::Idle);
    let (labels, semantic) = deck.sent();
    assert_eq!(labels.len(), 1, "{labels:?}");
    assert!(
        semantic.iter().all(Option::is_none),
        "a limited transition is still claimed: upstream's sound does not slip through"
    );
}

#[test]
fn panes_changing_together_sound_once_per_fleet_interval_unless_it_is_zero() {
    for (interval, expected) in [("", 1), ("fleet_min_interval_ms = 0\n", 2)] {
        let mut deck = Deck::new(&format!(
            "[ui.sound]\n{interval}[ui.sound.transitions]\n\"idle -> working\" = \"w.mp3\"\n"
        ));
        let other = deck.other_pane();
        deck.report(PaneAgentState::Idle);
        deck.report_on(other.clone(), PaneAgentState::Idle);
        let _ = deck.sent();
        deck.report(PaneAgentState::Working);
        deck.report_on(other, PaneAgentState::Working);
        let (labels, _) = deck.sent();
        assert_eq!(labels.len(), expected, "{interval:?}: {labels:?}");
    }
}
