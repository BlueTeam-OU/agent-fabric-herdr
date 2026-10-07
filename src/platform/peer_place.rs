//! Where a local-socket peer runs: inside a Herdr pane or not.
//!
//! A pane's shell is a session leader (the PTY spawn calls `setsid`) started
//! with `HERDR_ENV=1`, and a process's start-time environment cannot be
//! rewritten by its descendants. So a peer is inside a pane when the peer,
//! its session leader, or any ancestor is a session leader that started with
//! that marker. Plugin and custom commands share the server's session or run
//! without the marker, so they count as outside: they are the person's own
//! configured automation, not something typed into a pane.
//!
//! Same-account processes are not a security boundary; this stops the routine
//! route (the `herdr` CLI, an integration hook, a script run in a pane). A
//! process that detaches into a new session *and* clears its environment
//! escapes it, and so does anything started outside Herdr (cron, a service).

// Only Linux reads process facts today; elsewhere every peer is unidentified.
#![cfg_attr(not(target_os = "linux"), allow(dead_code))]

/// The verdict on one connecting process.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum PeerPlace {
    OutsidePanes,
    InsidePane,
    /// The peer could not be identified (no peer credentials on this platform,
    /// the process is gone, or its facts are unreadable). Guarded modes refuse it.
    Unidentified,
}

/// What the platform can say about a process. `None` means unreadable.
pub(crate) trait ProcessFacts {
    fn parent(&self, pid: u32) -> Option<u32>;
    fn session(&self, pid: u32) -> Option<u32>;
    /// Whether the process's start-time environment carries `HERDR_ENV=1`.
    fn started_in_herdr(&self, pid: u32) -> Option<bool>;
}

/// Ancestry is short in practice; the bound only guards against a cycle that
/// pid reuse could produce mid-walk.
const MAX_ANCESTRY_DEPTH: usize = 128;

pub(crate) fn classify_process(peer: u32, facts: &impl ProcessFacts) -> PeerPlace {
    // The peer's own environment must be readable: an unreadable peer is
    // another account (root) or already gone, and either way unidentified.
    if facts.started_in_herdr(peer).is_none() {
        return PeerPlace::Unidentified;
    }
    if let Some(leader) = facts.session(peer) {
        if is_pane_leader(leader, facts) {
            return PeerPlace::InsidePane;
        }
    }

    let mut pid = peer;
    for _ in 0..MAX_ANCESTRY_DEPTH {
        if is_pane_leader(pid, facts) {
            return PeerPlace::InsidePane;
        }
        match facts.parent(pid) {
            Some(parent) if parent > 1 && parent != pid => pid = parent,
            // An unreadable ancestor (a root-owned sudo, a vanished parent) ends
            // the walk; what was readable below it already had its say.
            _ => return PeerPlace::OutsidePanes,
        }
    }
    PeerPlace::Unidentified
}

fn is_pane_leader(pid: u32, facts: &impl ProcessFacts) -> bool {
    facts.session(pid) == Some(pid) && facts.started_in_herdr(pid) == Some(true)
}

/// Whether an environment block (NUL-separated `KEY=VALUE`) carries the marker.
pub(crate) fn environ_has_herdr_marker(environ: &[u8]) -> bool {
    let marker = format!("{}={}", crate::HERDR_ENV_VAR, crate::HERDR_ENV_VALUE);
    environ
        .split(|byte| *byte == 0)
        .any(|entry| entry == marker.as_bytes())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    #[derive(Default)]
    struct FakeProcess {
        parent: u32,
        session: u32,
        started_in_herdr: Option<bool>,
    }

    #[derive(Default)]
    struct FakeTable(HashMap<u32, FakeProcess>);

    impl FakeTable {
        fn with(mut self, pid: u32, parent: u32, session: u32, marker: Option<bool>) -> Self {
            self.0.insert(
                pid,
                FakeProcess {
                    parent,
                    session,
                    started_in_herdr: marker,
                },
            );
            self
        }
    }

    impl ProcessFacts for FakeTable {
        fn parent(&self, pid: u32) -> Option<u32> {
            self.0.get(&pid).map(|process| process.parent)
        }
        fn session(&self, pid: u32) -> Option<u32> {
            self.0.get(&pid).map(|process| process.session)
        }
        fn started_in_herdr(&self, pid: u32) -> Option<bool> {
            self.0
                .get(&pid)
                .and_then(|process| process.started_in_herdr)
        }
    }

    // pid 10: the server (own session, no marker); pid 20: a pane shell.
    fn herdr_with_one_pane() -> FakeTable {
        FakeTable::default()
            .with(1, 0, 1, Some(false))
            .with(10, 1, 10, Some(false))
            .with(20, 10, 20, Some(true))
    }

    #[test]
    fn a_command_run_in_a_pane_is_inside() {
        let table = herdr_with_one_pane().with(21, 20, 20, Some(true));
        assert_eq!(classify_process(21, &table), PeerPlace::InsidePane);
    }

    #[test]
    fn a_pane_command_with_a_cleared_environment_is_still_inside() {
        let table = herdr_with_one_pane().with(21, 20, 20, Some(false));
        assert_eq!(classify_process(21, &table), PeerPlace::InsidePane);
    }

    #[test]
    fn a_double_forked_pane_command_keeps_its_session_and_stays_inside() {
        // Reparented to init, but still in the pane shell's session.
        let table = herdr_with_one_pane().with(22, 1, 20, Some(false));
        assert_eq!(classify_process(22, &table), PeerPlace::InsidePane);
    }

    #[test]
    fn a_detached_pane_command_carries_the_marker_into_its_own_session() {
        let table = herdr_with_one_pane().with(23, 1, 23, Some(true));
        assert_eq!(classify_process(23, &table), PeerPlace::InsidePane);
    }

    #[test]
    fn a_pane_shell_after_live_handoff_is_inside() {
        // The old server exited; the pane shell now hangs off init.
        let table = FakeTable::default()
            .with(1, 0, 1, Some(false))
            .with(20, 1, 20, Some(true))
            .with(21, 20, 20, Some(true));
        assert_eq!(classify_process(21, &table), PeerPlace::InsidePane);
    }

    #[test]
    fn a_command_under_a_root_owned_sudo_in_a_pane_is_inside() {
        let table = herdr_with_one_pane()
            .with(30, 20, 20, None)
            .with(31, 30, 20, Some(true));
        assert_eq!(classify_process(31, &table), PeerPlace::InsidePane);
    }

    #[test]
    fn a_plugin_command_in_the_server_session_is_outside() {
        let table = herdr_with_one_pane().with(40, 10, 10, Some(true));
        assert_eq!(classify_process(40, &table), PeerPlace::OutsidePanes);
    }

    #[test]
    fn a_client_in_an_ordinary_terminal_is_outside() {
        let table =
            herdr_with_one_pane()
                .with(50, 1, 50, Some(false))
                .with(51, 50, 50, Some(false));
        assert_eq!(classify_process(51, &table), PeerPlace::OutsidePanes);
    }

    #[test]
    fn an_unreadable_peer_is_unidentified() {
        let table = herdr_with_one_pane().with(60, 1, 60, None);
        assert_eq!(classify_process(60, &table), PeerPlace::Unidentified);
        assert_eq!(classify_process(99, &table), PeerPlace::Unidentified);
    }

    #[test]
    fn a_parent_cycle_is_unidentified() {
        let table =
            FakeTable::default()
                .with(70, 71, 70, Some(false))
                .with(71, 70, 71, Some(false));
        assert_eq!(classify_process(70, &table), PeerPlace::Unidentified);
    }

    #[test]
    fn the_marker_must_be_a_whole_entry() {
        assert!(environ_has_herdr_marker(b"PATH=/bin\0HERDR_ENV=1\0"));
        assert!(environ_has_herdr_marker(b"HERDR_ENV=1"));
        assert!(!environ_has_herdr_marker(b"HERDR_ENV=10\0"));
        assert!(!environ_has_herdr_marker(b"XHERDR_ENV=1\0"));
        assert!(!environ_has_herdr_marker(b"HERDR_ENV=0\0"));
    }
}
