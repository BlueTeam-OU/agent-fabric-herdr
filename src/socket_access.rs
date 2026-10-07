//! `server.socket_access`: which local processes the server answers.
//!
//! Both sockets are 0600, so only this account reaches them; this narrows that
//! further, so a process inside a pane cannot drive other panes. The verdict
//! on a peer comes from [`crate::platform::local_stream_peer_place`]; this
//! module only decides, so the rules stay testable without sockets.

use std::sync::atomic::{AtomicU8, Ordering};
use std::sync::Arc;

use crate::config::SocketAccess;
use crate::platform::PeerPlace;

/// The enforced mode, shared by both accept paths and updated on config reload.
#[derive(Clone, Debug)]
pub(crate) struct SocketAccessGate(Arc<AtomicU8>);

impl SocketAccessGate {
    pub(crate) fn new(mode: SocketAccess) -> Self {
        Self(Arc::new(AtomicU8::new(encode(mode.effective()))))
    }

    pub(crate) fn set(&self, mode: SocketAccess) {
        self.0.store(encode(mode.effective()), Ordering::Relaxed);
    }

    pub(crate) fn mode(&self) -> SocketAccess {
        decode(self.0.load(Ordering::Relaxed))
    }
}

impl Default for SocketAccessGate {
    fn default() -> Self {
        Self::new(SocketAccess::All)
    }
}

fn encode(mode: SocketAccess) -> u8 {
    match mode {
        SocketAccess::All => 0,
        SocketAccess::OutsidePanes => 1,
        SocketAccess::ClientOnly | SocketAccess::Unrecognized => 2,
    }
}

fn decode(value: u8) -> SocketAccess {
    match value {
        0 => SocketAccess::All,
        1 => SocketAccess::OutsidePanes,
        _ => SocketAccess::ClientOnly,
    }
}

/// What an API request needs, for access purposes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum ApiRequestKind {
    /// `ping`: version and capabilities. Always answered, so a client can
    /// still tell a running server from a dead one under every mode.
    Status,
    /// Herdr managing its own server: stop, live handoff, SSH agent
    /// registration by an attached remote client. Served under `client_only`.
    Lifecycle,
    /// Everything that reads or drives workspaces, panes and agents.
    Control,
}

pub(crate) const REFUSED_CODE: &str = "socket_access_refused";

/// Why the server refuses an API request, or `None` to serve it. `place` is
/// only evaluated when the mode needs it: placing a peer reads `/proc`.
pub(crate) fn api_refusal(
    mode: SocketAccess,
    kind: ApiRequestKind,
    place: impl FnOnce() -> PeerPlace,
) -> Option<String> {
    if mode == SocketAccess::All || kind == ApiRequestKind::Status {
        return None;
    }
    if let Some(refusal) = place_refusal(mode, place()) {
        return Some(refusal);
    }
    (mode == SocketAccess::ClientOnly && kind == ApiRequestKind::Control).then(|| {
        "herdr serves only its attached client here (server.socket_access = \"client_only\"); \
         set it to \"outside_panes\" or \"all\" to use this command"
            .to_owned()
    })
}

/// Why the server refuses a client-socket connection, or `None` to accept it.
pub(crate) fn client_refusal(
    mode: SocketAccess,
    place: impl FnOnce() -> PeerPlace,
) -> Option<String> {
    if mode == SocketAccess::All {
        return None;
    }
    place_refusal(mode, place())
}

fn place_refusal(mode: SocketAccess, place: PeerPlace) -> Option<String> {
    let setting = setting_name(mode);
    match place {
        PeerPlace::OutsidePanes => None,
        PeerPlace::InsidePane => Some(format!(
            "herdr refuses processes inside its panes (server.socket_access = \"{setting}\"); \
             run this from a terminal outside herdr"
        )),
        PeerPlace::Unidentified => Some(format!(
            "herdr could not tell whether this process runs inside one of its panes, \
             and server.socket_access = \"{setting}\" refuses what it cannot place"
        )),
    }
}

fn setting_name(mode: SocketAccess) -> &'static str {
    match mode.effective() {
        SocketAccess::All => "all",
        SocketAccess::OutsidePanes => "outside_panes",
        SocketAccess::ClientOnly | SocketAccess::Unrecognized => "client_only",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const MODES: [SocketAccess; 3] = [
        SocketAccess::All,
        SocketAccess::OutsidePanes,
        SocketAccess::ClientOnly,
    ];
    const KINDS: [ApiRequestKind; 3] = [
        ApiRequestKind::Status,
        ApiRequestKind::Lifecycle,
        ApiRequestKind::Control,
    ];
    const PLACES: [PeerPlace; 3] = [
        PeerPlace::OutsidePanes,
        PeerPlace::InsidePane,
        PeerPlace::Unidentified,
    ];

    fn served(mode: SocketAccess, kind: ApiRequestKind, place: PeerPlace) -> bool {
        api_refusal(mode, kind, || place).is_none()
    }

    #[test]
    fn all_serves_everyone_without_placing_the_peer() {
        for kind in KINDS {
            assert!(api_refusal(SocketAccess::All, kind, || panic!("placed")).is_none());
        }
        assert!(client_refusal(SocketAccess::All, || panic!("placed")).is_none());
    }

    #[test]
    fn status_is_answered_under_every_mode_without_placing_the_peer() {
        for mode in MODES {
            assert!(api_refusal(mode, ApiRequestKind::Status, || panic!("placed")).is_none());
        }
    }

    #[test]
    fn guarded_modes_refuse_pane_and_unplaced_peers_everything_but_status() {
        for mode in [SocketAccess::OutsidePanes, SocketAccess::ClientOnly] {
            for place in [PeerPlace::InsidePane, PeerPlace::Unidentified] {
                for kind in [ApiRequestKind::Lifecycle, ApiRequestKind::Control] {
                    assert!(!served(mode, kind, place), "{mode:?} {kind:?} {place:?}");
                }
                assert!(client_refusal(mode, || place).is_some());
            }
        }
    }

    #[test]
    fn outside_panes_serves_every_request_from_outside() {
        for kind in KINDS {
            assert!(served(
                SocketAccess::OutsidePanes,
                kind,
                PeerPlace::OutsidePanes
            ));
        }
        assert!(client_refusal(SocketAccess::OutsidePanes, || PeerPlace::OutsidePanes).is_none());
    }

    #[test]
    fn client_only_serves_lifecycle_and_clients_but_no_control() {
        let outside = PeerPlace::OutsidePanes;
        assert!(served(
            SocketAccess::ClientOnly,
            ApiRequestKind::Lifecycle,
            outside
        ));
        assert!(!served(
            SocketAccess::ClientOnly,
            ApiRequestKind::Control,
            outside
        ));
        assert!(client_refusal(SocketAccess::ClientOnly, || outside).is_none());
    }

    #[test]
    fn every_mode_place_and_kind_has_one_answer() {
        // Exhaustive table: the rule, not the instances above.
        for mode in MODES {
            for kind in KINDS {
                for place in PLACES {
                    let expected = match (mode, kind, place) {
                        (SocketAccess::All, _, _) | (_, ApiRequestKind::Status, _) => true,
                        (_, _, PeerPlace::InsidePane | PeerPlace::Unidentified) => false,
                        (SocketAccess::ClientOnly, ApiRequestKind::Control, _) => false,
                        _ => true,
                    };
                    assert_eq!(
                        served(mode, kind, place),
                        expected,
                        "{mode:?} {kind:?} {place:?}"
                    );
                }
            }
        }
    }

    #[test]
    fn refusals_name_the_setting_in_force() {
        let refusal = api_refusal(SocketAccess::OutsidePanes, ApiRequestKind::Control, || {
            PeerPlace::InsidePane
        })
        .unwrap_or_default();
        assert!(refusal.contains("\"outside_panes\""), "{refusal}");
    }

    #[test]
    fn an_unrecognized_value_is_enforced_as_client_only() {
        let gate = SocketAccessGate::new(SocketAccess::Unrecognized);
        assert_eq!(gate.mode(), SocketAccess::ClientOnly);
        gate.set(SocketAccess::OutsidePanes);
        assert_eq!(gate.mode(), SocketAccess::OutsidePanes);
        gate.set(SocketAccess::All);
        assert_eq!(gate.mode(), SocketAccess::All);
    }
}
