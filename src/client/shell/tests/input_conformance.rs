//! Keyboard transparency conformance.
//!
//! Herdr should be invisible to the application in a pane: for every keystroke,
//! the pane must receive the bytes it would receive running directly in the
//! host terminal. The oracle is libghostty's encoder fed the same key event the
//! Ghostty app builds from an OS key event. The Herdr path is the real one:
//! host bytes -> host framer -> client shell routing -> server pane input ->
//! pane encoder, with the pane's modes set by application output.
//!
//! Keystrokes whose host bytes cannot distinguish keys the pane would see
//! differently are counted as host-lossy, not as Herdr failures.

use std::collections::{BTreeMap, HashMap};

use super::*;

use crate::ghostty::{self, ffi};

#[derive(Clone, Copy)]
struct KeyDef {
    name: &'static str,
    key: ffi::GhosttyKey,
    /// US layout text: (unshifted, shifted).
    text: Option<(char, char)>,
}

const fn text(name: &'static str, key: ffi::GhosttyKey, base: char, shifted: char) -> KeyDef {
    KeyDef {
        name,
        key,
        text: Some((base, shifted)),
    }
}

const fn func(name: &'static str, key: ffi::GhosttyKey) -> KeyDef {
    KeyDef {
        name,
        key,
        text: None,
    }
}

const KEYS: &[KeyDef] = &[
    text("a", ffi::GhosttyKey_GHOSTTY_KEY_A, 'a', 'A'),
    text("b", ffi::GhosttyKey_GHOSTTY_KEY_B, 'b', 'B'),
    text("c", ffi::GhosttyKey_GHOSTTY_KEY_C, 'c', 'C'),
    text("d", ffi::GhosttyKey_GHOSTTY_KEY_D, 'd', 'D'),
    text("e", ffi::GhosttyKey_GHOSTTY_KEY_E, 'e', 'E'),
    text("f", ffi::GhosttyKey_GHOSTTY_KEY_F, 'f', 'F'),
    text("g", ffi::GhosttyKey_GHOSTTY_KEY_G, 'g', 'G'),
    text("h", ffi::GhosttyKey_GHOSTTY_KEY_H, 'h', 'H'),
    text("i", ffi::GhosttyKey_GHOSTTY_KEY_I, 'i', 'I'),
    text("j", ffi::GhosttyKey_GHOSTTY_KEY_J, 'j', 'J'),
    text("k", ffi::GhosttyKey_GHOSTTY_KEY_K, 'k', 'K'),
    text("l", ffi::GhosttyKey_GHOSTTY_KEY_L, 'l', 'L'),
    text("m", ffi::GhosttyKey_GHOSTTY_KEY_M, 'm', 'M'),
    text("n", ffi::GhosttyKey_GHOSTTY_KEY_N, 'n', 'N'),
    text("o", ffi::GhosttyKey_GHOSTTY_KEY_O, 'o', 'O'),
    text("p", ffi::GhosttyKey_GHOSTTY_KEY_P, 'p', 'P'),
    text("q", ffi::GhosttyKey_GHOSTTY_KEY_Q, 'q', 'Q'),
    text("r", ffi::GhosttyKey_GHOSTTY_KEY_R, 'r', 'R'),
    text("s", ffi::GhosttyKey_GHOSTTY_KEY_S, 's', 'S'),
    text("t", ffi::GhosttyKey_GHOSTTY_KEY_T, 't', 'T'),
    text("u", ffi::GhosttyKey_GHOSTTY_KEY_U, 'u', 'U'),
    text("v", ffi::GhosttyKey_GHOSTTY_KEY_V, 'v', 'V'),
    text("w", ffi::GhosttyKey_GHOSTTY_KEY_W, 'w', 'W'),
    text("x", ffi::GhosttyKey_GHOSTTY_KEY_X, 'x', 'X'),
    text("y", ffi::GhosttyKey_GHOSTTY_KEY_Y, 'y', 'Y'),
    text("z", ffi::GhosttyKey_GHOSTTY_KEY_Z, 'z', 'Z'),
    text("0", ffi::GhosttyKey_GHOSTTY_KEY_DIGIT_0, '0', ')'),
    text("1", ffi::GhosttyKey_GHOSTTY_KEY_DIGIT_1, '1', '!'),
    text("2", ffi::GhosttyKey_GHOSTTY_KEY_DIGIT_2, '2', '@'),
    text("3", ffi::GhosttyKey_GHOSTTY_KEY_DIGIT_3, '3', '#'),
    text("4", ffi::GhosttyKey_GHOSTTY_KEY_DIGIT_4, '4', '$'),
    text("5", ffi::GhosttyKey_GHOSTTY_KEY_DIGIT_5, '5', '%'),
    text("6", ffi::GhosttyKey_GHOSTTY_KEY_DIGIT_6, '6', '^'),
    text("7", ffi::GhosttyKey_GHOSTTY_KEY_DIGIT_7, '7', '&'),
    text("8", ffi::GhosttyKey_GHOSTTY_KEY_DIGIT_8, '8', '*'),
    text("9", ffi::GhosttyKey_GHOSTTY_KEY_DIGIT_9, '9', '('),
    text("`", ffi::GhosttyKey_GHOSTTY_KEY_BACKQUOTE, '`', '~'),
    text("-", ffi::GhosttyKey_GHOSTTY_KEY_MINUS, '-', '_'),
    text("=", ffi::GhosttyKey_GHOSTTY_KEY_EQUAL, '=', '+'),
    text("[", ffi::GhosttyKey_GHOSTTY_KEY_BRACKET_LEFT, '[', '{'),
    text("]", ffi::GhosttyKey_GHOSTTY_KEY_BRACKET_RIGHT, ']', '}'),
    text("\\", ffi::GhosttyKey_GHOSTTY_KEY_BACKSLASH, '\\', '|'),
    text(";", ffi::GhosttyKey_GHOSTTY_KEY_SEMICOLON, ';', ':'),
    text("'", ffi::GhosttyKey_GHOSTTY_KEY_QUOTE, '\'', '"'),
    text(",", ffi::GhosttyKey_GHOSTTY_KEY_COMMA, ',', '<'),
    text(".", ffi::GhosttyKey_GHOSTTY_KEY_PERIOD, '.', '>'),
    text("/", ffi::GhosttyKey_GHOSTTY_KEY_SLASH, '/', '?'),
    text("space", ffi::GhosttyKey_GHOSTTY_KEY_SPACE, ' ', ' '),
    func("enter", ffi::GhosttyKey_GHOSTTY_KEY_ENTER),
    func("tab", ffi::GhosttyKey_GHOSTTY_KEY_TAB),
    func("backspace", ffi::GhosttyKey_GHOSTTY_KEY_BACKSPACE),
    func("escape", ffi::GhosttyKey_GHOSTTY_KEY_ESCAPE),
    func("up", ffi::GhosttyKey_GHOSTTY_KEY_ARROW_UP),
    func("down", ffi::GhosttyKey_GHOSTTY_KEY_ARROW_DOWN),
    func("left", ffi::GhosttyKey_GHOSTTY_KEY_ARROW_LEFT),
    func("right", ffi::GhosttyKey_GHOSTTY_KEY_ARROW_RIGHT),
    func("home", ffi::GhosttyKey_GHOSTTY_KEY_HOME),
    func("end", ffi::GhosttyKey_GHOSTTY_KEY_END),
    func("pageup", ffi::GhosttyKey_GHOSTTY_KEY_PAGE_UP),
    func("pagedown", ffi::GhosttyKey_GHOSTTY_KEY_PAGE_DOWN),
    func("insert", ffi::GhosttyKey_GHOSTTY_KEY_INSERT),
    func("delete", ffi::GhosttyKey_GHOSTTY_KEY_DELETE),
    func("f1", ffi::GhosttyKey_GHOSTTY_KEY_F1),
    func("f2", ffi::GhosttyKey_GHOSTTY_KEY_F2),
    func("f3", ffi::GhosttyKey_GHOSTTY_KEY_F3),
    func("f4", ffi::GhosttyKey_GHOSTTY_KEY_F4),
    func("f5", ffi::GhosttyKey_GHOSTTY_KEY_F5),
    func("f6", ffi::GhosttyKey_GHOSTTY_KEY_F6),
    func("f7", ffi::GhosttyKey_GHOSTTY_KEY_F7),
    func("f8", ffi::GhosttyKey_GHOSTTY_KEY_F8),
    func("f9", ffi::GhosttyKey_GHOSTTY_KEY_F9),
    func("f10", ffi::GhosttyKey_GHOSTTY_KEY_F10),
    func("f11", ffi::GhosttyKey_GHOSTTY_KEY_F11),
    func("f12", ffi::GhosttyKey_GHOSTTY_KEY_F12),
];

/// Modes an application can request by writing to its terminal.
const PANE_MODES: &[(&str, &[u8])] = &[
    ("legacy", b""),
    ("legacy+decckm", b"\x1b[?1h"),
    ("modifyOtherKeys1", b"\x1b[>4;1m"),
    ("modifyOtherKeys2", b"\x1b[>4;2m"),
    ("kitty1", b"\x1b[>1u"),
    ("kitty3", b"\x1b[>3u"),
    ("kitty7", b"\x1b[>7u"),
    ("kitty11", b"\x1b[>11u"),
    ("kitty15", b"\x1b[>15u"),
    ("kitty31", b"\x1b[>31u"),
];

#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
enum HostProfile {
    /// Kitty keyboard host (Ghostty, kitty, WezTerm, foot...). Herdr pushes 7,
    /// or 31 while the pane wants all keys reported.
    Kitty,
    /// Host without an enhanced keyboard protocol.
    Legacy,
}

impl HostProfile {
    fn name(self) -> &'static str {
        match self {
            Self::Kitty => "kitty-host",
            Self::Legacy => "legacy-host",
        }
    }

    fn setup(self, pane_mode: &[u8]) -> &'static [u8] {
        match self {
            Self::Kitty if pane_mode == b"\x1b[>11u" || pane_mode == b"\x1b[>15u" => b"\x1b[>31u",
            Self::Kitty if pane_mode == b"\x1b[>31u" => b"\x1b[>31u",
            Self::Kitty => b"\x1b[>7u",
            Self::Legacy => b"",
        }
    }
}

const MODS: [(u16, &str); 4] = [
    (ghostty::MOD_CTRL, "ctrl"),
    (ghostty::MOD_ALT, "alt"),
    (ghostty::MOD_SHIFT, "shift"),
    (ghostty::MOD_SUPER, "super"),
];

fn mods_name(mods: u16) -> String {
    let mut parts: Vec<&str> = MODS
        .iter()
        .filter(|(bit, _)| mods & bit != 0)
        .map(|(_, name)| *name)
        .collect();
    if parts.is_empty() {
        parts.push("plain");
    }
    parts.join("+")
}

/// Host bytes for one keystroke: (press, release).
type HostKeystroke = (Vec<u8>, Vec<u8>);

struct Oracle {
    _terminal: ghostty::Terminal,
    encoder: ghostty::KeyEncoder,
}

impl Oracle {
    fn new(app_output: &[u8]) -> Self {
        let mut terminal = ghostty::Terminal::new(80, 24, 0).expect("terminal");
        terminal.write(app_output);
        let mut encoder = ghostty::KeyEncoder::new().expect("encoder");
        encoder.set_from_terminal(&terminal);
        Self {
            _terminal: terminal,
            encoder,
        }
    }

    /// Bytes for one keystroke (press then release), built like the Ghostty app
    /// builds key events from the OS: physical key, modifiers, layout text, the
    /// unshifted codepoint, and Shift consumed when it produced the text.
    fn keystroke(&mut self, def: KeyDef, mods: u16) -> HostKeystroke {
        let press = self.encode(def, mods, ffi::GhosttyKeyAction_GHOSTTY_KEY_ACTION_PRESS);
        let release = self.encode(def, mods, ffi::GhosttyKeyAction_GHOSTTY_KEY_ACTION_RELEASE);
        (press, release)
    }

    fn encode(&mut self, def: KeyDef, mods: u16, action: ffi::GhosttyKeyAction) -> Vec<u8> {
        let mut event = ghostty::KeyEvent::new().expect("key event");
        event.set_key(def.key);
        event.set_mods(mods);
        event.set_action(action);
        let utf8;
        if let Some((base, shifted)) = def.text {
            let shift = mods & ghostty::MOD_SHIFT != 0;
            utf8 = if shift { shifted } else { base }.to_string();
            event.set_utf8(&utf8);
            event.set_unshifted_codepoint(base as u32);
            if shift && shifted != base {
                event.set_consumed_mods(ghostty::MOD_SHIFT);
            }
        }
        self.encoder.encode(&event).expect("encode")
    }
}

/// Panes that negotiated nothing. Like Ghostty, modifyOtherKeys level 1 counts
/// as nothing.
fn is_legacy_pane(pane_mode: &[u8]) -> bool {
    matches!(pane_mode, b"" | b"\x1b[?1h" | b"\x1b[>4;1m")
}

/// Agreed exception table: panes that negotiated no keyboard protocol keep the
/// classic bytes for keys where Ghostty's escape sequences break shells, and
/// get Super chords as basic Kitty reports (see `is_legacy_pane` use above).
fn legacy_shell_exception(pane_mode: &[u8], key: &str, mods: u16) -> Option<Vec<u8>> {
    if !is_legacy_pane(pane_mode) {
        return None;
    }
    let alt = mods & ghostty::MOD_ALT != 0;
    let base = mods & !ghostty::MOD_ALT;
    let classic: &[u8] = match (key, base) {
        ("enter", m) if m != 0 => b"\r",
        ("m", ghostty::MOD_CTRL) => b"\r",
        ("i", ghostty::MOD_CTRL) | ("tab", ghostty::MOD_CTRL) => b"\t",
        ("[", ghostty::MOD_CTRL) => b"\x1b",
        _ => return None,
    };
    Some(if alt {
        [b"\x1b", classic].concat()
    } else {
        classic.to_vec()
    })
}

struct HerdrPath {
    state: ClientShellState,
    framer: crate::raw_input::RawInputByteFramer,
    runtime: crate::terminal::TerminalRuntime,
    rx: tokio::sync::mpsc::Receiver<bytes::Bytes>,
    host: HostProfile,
}

impl HerdrPath {
    fn new(host: HostProfile, app_output: &[u8]) -> Self {
        let (runtime, mut rx) =
            crate::terminal::TerminalRuntime::test_with_channel_and_scrollback_bytes(
                80, 24, 0, b"", 4096,
            );
        runtime.test_process_pty_bytes(app_output);
        while rx.try_recv().is_ok() {}
        Self {
            state: Self::fresh_state(host),
            framer: Self::fresh_framer(host),
            runtime,
            rx,
            host,
        }
    }

    fn fresh_state(host: HostProfile) -> ClientShellState {
        let mut state = ClientShellState::new(ClientShellConfig::from_config(&Config::default()));
        // Mirrors the client: Herdr pushes Kitty event types on Kitty hosts.
        state.set_host_reports_key_releases(host == HostProfile::Kitty);
        state.set_snapshot(Box::new(snapshot()));
        state.set_pane_surface(surface());
        state
    }

    fn fresh_framer(host: HostProfile) -> crate::raw_input::RawInputByteFramer {
        #[allow(unused_mut)] // only mutated on unix
        let mut framer = crate::raw_input::RawInputByteFramer::for_host_input();
        #[cfg(unix)]
        framer.set_host_escape_disambiguation_active(host == HostProfile::Kitty);
        #[cfg(not(unix))]
        let _ = host;
        framer
    }

    /// Collect pane input from one client outcome, the way the client loop does:
    /// side requests (pane focus) are ignored, link lookups get a no-link answer
    /// and the held mouse events are replayed. Returns true when Herdr kept the
    /// input for itself.
    fn absorb(
        &mut self,
        outcome: ClientShellInput,
        events: &mut Vec<ClientPaneInputEvent>,
    ) -> bool {
        let mut owned = outcome.detach;
        for request in outcome.requests {
            if let ClientMessage::ClientShellPaneInput { events: batch, .. } = request {
                events.extend(batch);
            }
        }
        let mut replay = Vec::new();
        for action in outcome.actions {
            match action {
                ClientShellAction::Endpoint {
                    boot_id, request, ..
                } if matches!(
                    request.method,
                    crate::api::schema::Method::PaneLinkActivate(_)
                ) =>
                {
                    let (_, actions) = self.state.handle_endpoint_result(
                        &boot_id,
                        &request.id,
                        Ok(crate::api::schema::ResponseResult::PaneLinkActivated {
                            url: None,
                            handled: false,
                        }),
                    );
                    for action in actions {
                        match action {
                            ClientShellAction::ReplayMouse(mouse) => replay.extend(mouse),
                            _ => owned = true,
                        }
                    }
                }
                ClientShellAction::Endpoint { .. } => {}
                ClientShellAction::ReplayMouse(mouse) => replay.extend(mouse),
                _ => owned = true,
            }
        }
        if !replay.is_empty() {
            let outcome = self.state.replay_mouse_events(replay);
            owned |= self.absorb(outcome, events);
        }
        owned
    }

    fn reset_client(&mut self) {
        self.state = Self::fresh_state(self.host);
        self.framer = Self::fresh_framer(self.host);
    }

    /// Feed one host write, then let idle flushes run. Returns None when Herdr
    /// itself consumed the key (prefix, binding, mode change).
    fn feed(&mut self, host_bytes: &[u8]) -> Option<Vec<u8>> {
        let mut chunks = self.framer.push(host_bytes);
        for _ in 0..3 {
            if !self.framer.has_pending_input() {
                break;
            }
            chunks.extend(self.framer.flush_timeout());
        }
        let mut events = Vec::new();
        let mut herdr_owned = false;
        for chunk in chunks {
            let outcome = self.state.handle_input_bytes(&chunk);
            herdr_owned |= self.absorb(outcome, &mut events);
        }
        herdr_owned |= self.state.mode != ClientShellMode::Terminal || self.state.overlay.is_some();
        if herdr_owned {
            return None;
        }
        let mut out = Vec::new();
        if let Err(err) =
            crate::server::pane_input::test_apply_client_pane_input_events(&self.runtime, &events)
        {
            out.extend_from_slice(format!("<server error: {err}>").as_bytes());
        }
        while let Ok(bytes) = self.rx.try_recv() {
            out.extend_from_slice(&bytes);
        }
        Some(out)
    }
}

/// Kitty's default event type is press, so `;mods:1` and `;mods` are the same
/// report. Strip the explicit form so equivalent encodings compare equal.
fn normalize_kitty_press(bytes: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i..].starts_with(b":1")
            && bytes
                .get(i + 2)
                .is_some_and(|b| matches!(b, b'u' | b'~' | b';') || b.is_ascii_uppercase())
        {
            i += 2;
            continue;
        }
        out.push(bytes[i]);
        i += 1;
    }
    out
}

#[derive(Default)]
struct Tally {
    scored: usize,
    passed: usize,
    equivalent: usize,
    host_lossy: usize,
    herdr_owned: usize,
}

struct Failure {
    host: &'static str,
    pane: &'static str,
    keystroke: String,
    expected: Vec<u8>,
    actual: Vec<u8>,
}

fn show(bytes: &[u8]) -> String {
    bytes.escape_ascii().to_string()
}

struct Report {
    by_cell: BTreeMap<(&'static str, &'static str, &'static str), Tally>,
    failures: Vec<Failure>,
    owned: Vec<String>,
}

fn run_keyboard_conformance() -> Report {
    let mut report = Report {
        by_cell: BTreeMap::new(),
        failures: Vec::new(),
        owned: Vec::new(),
    };
    for host in [HostProfile::Kitty, HostProfile::Legacy] {
        for &(pane_name, pane_mode) in PANE_MODES {
            let mut host_oracle = Oracle::new(host.setup(pane_mode));
            let mut direct_oracle = Oracle::new(pane_mode);
            let mut disambiguate_oracle = Oracle::new(b"\x1b[>1u");

            let mut cases = Vec::new();
            for def in KEYS {
                for mods in 0u16..16 {
                    let mods = MODS
                        .iter()
                        .enumerate()
                        .filter(|(i, _)| mods & (1 << i) != 0)
                        .fold(0, |acc, (_, (bit, _))| acc | bit);
                    let host_bytes = host_oracle.keystroke(*def, mods);
                    let (mut press, release) = direct_oracle.keystroke(*def, mods);
                    if let Some(classic) = legacy_shell_exception(pane_mode, def.name, mods) {
                        press = classic;
                    } else if is_legacy_pane(pane_mode) && mods & ghostty::MOD_SUPER != 0 {
                        press = disambiguate_oracle.keystroke(*def, mods).0;
                    }
                    // A host that never reports releases gives nobody a release to forward.
                    let expected = if host_bytes.1.is_empty() {
                        press
                    } else {
                        [press, release].concat()
                    };
                    cases.push((*def, mods, host_bytes, expected));
                }
            }

            let mut expected_by_host_bytes: HashMap<&HostKeystroke, Vec<&Vec<u8>>> = HashMap::new();
            for (_, mods, host_bytes, expected) in &cases {
                if host == HostProfile::Legacy && mods & ghostty::MOD_SUPER != 0 {
                    continue;
                }
                expected_by_host_bytes
                    .entry(host_bytes)
                    .or_default()
                    .push(expected);
            }

            let mut herdr = HerdrPath::new(host, pane_mode);
            for (def, mods, host_bytes, expected) in &cases {
                let group = if mods & ghostty::MOD_SUPER != 0 {
                    "super"
                } else {
                    "core"
                };
                let tally = report
                    .by_cell
                    .entry((host.name(), pane_name, group))
                    .or_default();
                // Legacy hosts cannot report Super at all (they drop it or send
                // the chord without it), so nothing downstream can recover it.
                let super_unreportable =
                    host == HostProfile::Legacy && mods & ghostty::MOD_SUPER != 0;
                let ambiguous = expected_by_host_bytes
                    .get(host_bytes)
                    .is_some_and(|distinct| distinct.iter().any(|other| *other != expected));
                if super_unreportable || ambiguous {
                    tally.host_lossy += 1;
                    continue;
                }
                let press = herdr.feed(&host_bytes.0);
                let release = herdr.feed(&host_bytes.1);
                let page_key_scrolls_herdr = *mods == 0
                    && matches!(def.name, "pageup" | "pagedown")
                    && herdr.runtime.plain_page_keys_use_host_scrollback() == Some(true);
                let (Some(press), Some(release), false) = (press, release, page_key_scrolls_herdr)
                else {
                    tally.herdr_owned += 1;
                    herdr.reset_client();
                    continue;
                };
                let actual = [press, release].concat();
                tally.scored += 1;
                if &actual == expected {
                    tally.passed += 1;
                } else if normalize_kitty_press(&actual) == normalize_kitty_press(expected) {
                    tally.passed += 1;
                    tally.equivalent += 1;
                } else {
                    report.failures.push(Failure {
                        host: host.name(),
                        pane: pane_name,
                        keystroke: format!("{}+{}", mods_name(*mods), def.name),
                        expected: expected.clone(),
                        actual,
                    });
                }
            }
        }
    }
    report
}

fn print_report(report: &Report) {
    let mut total = Tally::default();
    println!(
        "\n{:<12} {:<17} {:<6} {:>7} {:>7} {:>7} {:>7} {:>7} {:>7}",
        "host", "pane", "keys", "scored", "passed", "score", "equiv", "lossy", "owned"
    );
    for ((host, pane, group), tally) in &report.by_cell {
        println!(
            "{:<12} {:<17} {:<6} {:>7} {:>7} {:>6.1}% {:>7} {:>7} {:>7}",
            host,
            pane,
            group,
            tally.scored,
            tally.passed,
            100.0 * tally.passed as f64 / tally.scored.max(1) as f64,
            tally.equivalent,
            tally.host_lossy,
            tally.herdr_owned
        );
        total.scored += tally.scored;
        total.passed += tally.passed;
        total.equivalent += tally.equivalent;
        total.host_lossy += tally.host_lossy;
        total.herdr_owned += tally.herdr_owned;
    }
    println!(
        "{:<37} {:>7} {:>7} {:>6.1}% {:>7} {:>7} {:>7}",
        "TOTAL",
        total.scored,
        total.passed,
        100.0 * total.passed as f64 / total.scored.max(1) as f64,
        total.equivalent,
        total.host_lossy,
        total.herdr_owned
    );

    if let Ok(path) = std::env::var("HERDR_INPUT_CONFORMANCE_FAILURES") {
        let lines: Vec<String> = report
            .failures
            .iter()
            .map(|failure| {
                format!(
                    "{}\t{}\t{}\texpected={}\tactual={}",
                    failure.host,
                    failure.pane,
                    failure.keystroke,
                    show(&failure.expected),
                    show(&failure.actual)
                )
            })
            .chain(report.owned.iter().map(|owned| format!("owned\t{owned}")))
            .collect();
        std::fs::write(path, lines.join("\n")).expect("write failures");
    }
}

// Ratchet: failure counts may only go down. Lower them when a change fixes
// cases; a rise means a regression in Herdr's input transparency.
const KEYBOARD_FAILURES_BASELINE: usize = 120;
const MOUSE_FAILURES_BASELINE: usize = 96;
const SPLIT_IDLE_MISMATCH_BASELINE: usize = 6_730;
const REPLY_IDLE_MISMATCH_BASELINE: usize = 77;

// ---------------------------------------------------------------------------
// Mouse
// ---------------------------------------------------------------------------

const MOUSE_TRACKING: &[(&str, &[u8])] = &[
    ("off", b""),
    ("x10", b"\x1b[?9h"),
    ("normal", b"\x1b[?1000h"),
    ("button", b"\x1b[?1002h"),
    ("any", b"\x1b[?1003h"),
];

const MOUSE_FORMATS: &[(&str, &[u8])] = &[
    ("default", b""),
    ("utf8", b"\x1b[?1005h"),
    ("sgr", b"\x1b[?1006h"),
    ("urxvt", b"\x1b[?1015h"),
];

/// What Herdr asks the host for while it captures the mouse.
const HOST_MOUSE_SETUP: &[u8] = b"\x1b[?1003h\x1b[?1006h";

#[derive(Clone, Copy)]
struct MouseStep {
    action: ffi::GhosttyMouseAction,
    button: Option<ffi::GhosttyMouseButton>,
    /// Offset added to the gesture's start cell.
    dx: u16,
    dy: u16,
}

const fn step(
    action: ffi::GhosttyMouseAction,
    button: Option<ffi::GhosttyMouseButton>,
    dx: u16,
    dy: u16,
) -> MouseStep {
    MouseStep {
        action,
        button,
        dx,
        dy,
    }
}

const GESTURES: &[(&str, &[MouseStep])] = &[
    (
        "click-left",
        &[
            step(
                ghostty::MOUSE_ACTION_PRESS,
                Some(ghostty::MOUSE_BUTTON_LEFT),
                0,
                0,
            ),
            step(
                ghostty::MOUSE_ACTION_RELEASE,
                Some(ghostty::MOUSE_BUTTON_LEFT),
                0,
                0,
            ),
        ],
    ),
    (
        "click-middle",
        &[
            step(
                ghostty::MOUSE_ACTION_PRESS,
                Some(ghostty::MOUSE_BUTTON_MIDDLE),
                0,
                0,
            ),
            step(
                ghostty::MOUSE_ACTION_RELEASE,
                Some(ghostty::MOUSE_BUTTON_MIDDLE),
                0,
                0,
            ),
        ],
    ),
    (
        "click-right",
        &[
            step(
                ghostty::MOUSE_ACTION_PRESS,
                Some(ghostty::MOUSE_BUTTON_RIGHT),
                0,
                0,
            ),
            step(
                ghostty::MOUSE_ACTION_RELEASE,
                Some(ghostty::MOUSE_BUTTON_RIGHT),
                0,
                0,
            ),
        ],
    ),
    (
        "drag-left",
        &[
            step(
                ghostty::MOUSE_ACTION_PRESS,
                Some(ghostty::MOUSE_BUTTON_LEFT),
                0,
                0,
            ),
            step(
                ghostty::MOUSE_ACTION_MOTION,
                Some(ghostty::MOUSE_BUTTON_LEFT),
                1,
                0,
            ),
            step(
                ghostty::MOUSE_ACTION_MOTION,
                Some(ghostty::MOUSE_BUTTON_LEFT),
                2,
                1,
            ),
            step(
                ghostty::MOUSE_ACTION_RELEASE,
                Some(ghostty::MOUSE_BUTTON_LEFT),
                2,
                1,
            ),
        ],
    ),
    (
        "move",
        &[
            step(ghostty::MOUSE_ACTION_MOTION, None, 0, 0),
            step(ghostty::MOUSE_ACTION_MOTION, None, 1, 1),
        ],
    ),
    (
        "wheel-up",
        &[step(
            ghostty::MOUSE_ACTION_PRESS,
            Some(ghostty::MOUSE_BUTTON_WHEEL_UP),
            0,
            0,
        )],
    ),
    (
        "wheel-down",
        &[step(
            ghostty::MOUSE_ACTION_PRESS,
            Some(ghostty::MOUSE_BUTTON_WHEEL_DOWN),
            0,
            0,
        )],
    ),
    (
        "wheel-left",
        &[step(
            ghostty::MOUSE_ACTION_PRESS,
            Some(ghostty::MOUSE_BUTTON_WHEEL_LEFT),
            0,
            0,
        )],
    ),
    (
        "wheel-right",
        &[step(
            ghostty::MOUSE_ACTION_PRESS,
            Some(ghostty::MOUSE_BUTTON_WHEEL_RIGHT),
            0,
            0,
        )],
    ),
];

const MOUSE_MODS: [(u16, &str); 4] = [
    (0, "plain"),
    (ghostty::MOD_SHIFT, "shift"),
    (ghostty::MOD_ALT, "alt"),
    (ghostty::MOD_CTRL, "ctrl"),
];

struct MouseOracle {
    _terminal: ghostty::Terminal,
    encoder: ghostty::MouseEncoder,
}

impl MouseOracle {
    fn new(app_output: &[u8], cols: u16, rows: u16) -> Self {
        let mut terminal = ghostty::Terminal::new(cols, rows, 0).expect("terminal");
        terminal.write(app_output);
        let mut encoder = ghostty::MouseEncoder::new().expect("encoder");
        encoder.set_from_terminal(&terminal);
        encoder.set_size(u32::from(cols), u32::from(rows), 1, 1);
        Self {
            _terminal: terminal,
            encoder,
        }
    }

    fn encode(&mut self, step: MouseStep, mods: u16, column: u16, row: u16) -> Vec<u8> {
        let mut event = ghostty::MouseEvent::new().expect("mouse event");
        event.set_action(step.action);
        match step.button {
            Some(button) => event.set_button(button),
            None => event.clear_button(),
        }
        event.set_mods(mods);
        event.set_position(f32::from(column), f32::from(row));
        self.encoder.encode(&event).expect("encode mouse")
    }
}

const MOUSE_PANE_COLS: u16 = 40;
const MOUSE_PANE_ROWS: u16 = 10;

fn mouse_surface(mouse_reporting: bool) -> PaneSurfaceFrame {
    let mut surface = surface();
    let pane = &mut surface.panes[0];
    for rect in [&mut pane.rect, &mut pane.inner_rect] {
        rect.width = MOUSE_PANE_COLS;
        rect.height = MOUSE_PANE_ROWS;
    }
    pane.mouse_reporting = mouse_reporting;
    surface
}

fn run_mouse_conformance() -> Report {
    let mut report = Report {
        by_cell: BTreeMap::new(),
        failures: Vec::new(),
        owned: Vec::new(),
    };
    for &(tracking_name, tracking) in MOUSE_TRACKING {
        for &(format_name, format) in MOUSE_FORMATS {
            let pane_mode = [tracking, format].concat();
            let pane_name: &'static str =
                Box::leak(format!("{tracking_name}/{format_name}").into_boxed_str());
            let tally = report
                .by_cell
                .entry(("kitty-host", pane_name, "mouse"))
                .or_default();

            let mut herdr = HerdrPath::new(HostProfile::Kitty, &pane_mode);
            herdr
                .state
                .set_pane_surface(mouse_surface(!tracking.is_empty()));
            herdr.state.compose(106, 20).expect("composed frame");
            let inner = herdr.state.hits.panes[0].inner_rect;
            let mut direct = MouseOracle::new(&pane_mode, 80, 24);
            let mut host = MouseOracle::new(HOST_MOUSE_SETUP, 106, 20);

            let starts = [
                (0u16, 0u16),
                (inner.width / 2, inner.height / 2),
                (
                    inner.width.saturating_sub(3),
                    inner.height.saturating_sub(2),
                ),
            ];
            for &(gesture_name, steps) in GESTURES {
                for &(mods, mods_label) in &MOUSE_MODS {
                    for &(column, row) in &starts {
                        let mut expected = Vec::new();
                        let mut actual = Vec::new();
                        let mut owned = false;
                        for step in steps {
                            let (c, r) = (column + step.dx, row + step.dy);
                            expected.extend(direct.encode(*step, mods, c, r));
                            let host_bytes = host.encode(*step, mods, inner.x + c, inner.y + r);
                            match herdr.feed(&host_bytes) {
                                Some(bytes) => actual.extend(bytes),
                                None => owned = true,
                            }
                        }
                        if owned {
                            tally.herdr_owned += 1;
                            report.owned.push(format!(
                                "{pane_name}\t{mods_label}+{gesture_name}@{column},{row}"
                            ));
                            herdr.reset_client();
                            herdr
                                .state
                                .set_pane_surface(mouse_surface(!tracking.is_empty()));
                            herdr.state.compose(106, 20).expect("composed frame");
                            continue;
                        }
                        tally.scored += 1;
                        if actual == expected {
                            tally.passed += 1;
                        } else {
                            report.failures.push(Failure {
                                host: "kitty-host",
                                pane: pane_name,
                                keystroke: format!("{mods_label}+{gesture_name}@{column},{row}"),
                                expected,
                                actual,
                            });
                        }
                    }
                }
            }
        }
    }
    report
}

// ---------------------------------------------------------------------------
// Split reads
// ---------------------------------------------------------------------------

fn host_input_corpus() -> Vec<(HostProfile, Vec<u8>)> {
    let mut corpus = Vec::new();
    for (host, setup) in [
        (HostProfile::Kitty, &b"\x1b[>7u"[..]),
        (HostProfile::Kitty, &b"\x1b[>31u"[..]),
        (HostProfile::Legacy, &b""[..]),
    ] {
        let mut oracle = Oracle::new(setup);
        for def in KEYS {
            for mods in [
                0,
                ghostty::MOD_SHIFT,
                ghostty::MOD_CTRL,
                ghostty::MOD_ALT,
                ghostty::MOD_CTRL | ghostty::MOD_SHIFT,
                ghostty::MOD_CTRL | ghostty::MOD_ALT,
            ] {
                let (press, release) = oracle.keystroke(*def, mods);
                corpus.push((host, press));
                if !release.is_empty() {
                    corpus.push((host, release));
                }
            }
        }
    }
    let mut mouse = MouseOracle::new(HOST_MOUSE_SETUP, 300, 100);
    for &(_, steps) in GESTURES {
        for &(mods, _) in &MOUSE_MODS {
            for step in steps {
                corpus.push((HostProfile::Kitty, mouse.encode(*step, mods, 7, 3)));
                corpus.push((HostProfile::Kitty, mouse.encode(*step, mods, 150, 42)));
            }
        }
    }
    corpus.sort();
    corpus.dedup();
    corpus.retain(|(_, bytes)| bytes.len() > 1);
    corpus
}

/// Replies Herdr asks the host for at startup and on focus (colors, palette,
/// cell size, appearance).
const HOST_REPLIES: &[&[u8]] = &[
    b"\x1b]10;rgb:ffff/ffff/ffff\x1b\\",
    b"\x1b]11;rgb:1e1e/1e1e/2e2e\x07",
    b"\x1b]11;rgb:1e1e/1e1e/2e2e\x1b\\",
    b"\x1b]4;1;rgb:cdcd/0000/0000\x1b\\",
    b"\x1b]4;255;rgb:eeee/eeee/eeee\x07",
    b"\x1b[6;20;10t",
    b"\x1b[?997;1n",
    b"\x1b[?997;2n",
];

fn framed_events(host: HostProfile, pieces: &[&[u8]], idle_between: bool) -> String {
    framed_events_with(host, pieces, idle_between, false)
}

fn framed_events_with(
    host: HostProfile,
    pieces: &[&[u8]],
    idle_between: bool,
    awaiting_replies: bool,
) -> String {
    let mut framer = HerdrPath::fresh_framer(host);
    if awaiting_replies {
        // Mirrors the Unix client right after it sent its host queries.
        framer.host_color_query_sent();
        framer.enable_host_color_scheme_change_tracking();
        framer.enable_host_appearance_query_on_focus();
        framer.host_cell_size_query_sent();
    }
    let mut chunks = Vec::new();
    for piece in pieces {
        chunks.extend(framer.push(piece));
        if idle_between {
            chunks.extend(framer.flush_timeout());
        }
    }
    for _ in 0..3 {
        if !framer.has_pending_input() {
            break;
        }
        chunks.extend(framer.flush_timeout());
    }
    let events: Vec<_> = chunks
        .iter()
        .flat_map(|chunk| crate::raw_input::parse_raw_input_bytes_sync(chunk))
        .collect();
    format!("{events:?}")
}

#[test]
fn split_read_robustness() {
    let corpus = host_input_corpus();
    let mut splits = 0usize;
    let mut burst_mismatch = Vec::new();
    let mut idle_mismatch = Vec::new();
    for (host, bytes) in &corpus {
        let whole = framed_events(*host, &[bytes], false);
        for cut in 1..bytes.len() {
            splits += 1;
            let pieces = [&bytes[..cut], &bytes[cut..]];
            if framed_events(*host, &pieces, false) != whole {
                burst_mismatch.push(format!(
                    "{}\t{}|{}",
                    host.name(),
                    show(pieces[0]),
                    show(pieces[1])
                ));
            }
            if framed_events(*host, &pieces, true) != whole {
                idle_mismatch.push(format!(
                    "{}\t{}|{}",
                    host.name(),
                    show(pieces[0]),
                    show(pieces[1])
                ));
            }
        }
    }
    let mut reply_splits = 0usize;
    let mut reply_burst_mismatch = Vec::new();
    let mut reply_idle_mismatch = Vec::new();
    for reply in HOST_REPLIES {
        let whole = framed_events_with(HostProfile::Kitty, &[reply], false, true);
        for cut in 1..reply.len() {
            reply_splits += 1;
            let pieces = [&reply[..cut], &reply[cut..]];
            let line = format!("reply\t{}|{}", show(pieces[0]), show(pieces[1]));
            if framed_events_with(HostProfile::Kitty, &pieces, false, true) != whole {
                reply_burst_mismatch.push(line.clone());
            }
            if framed_events_with(HostProfile::Kitty, &pieces, true, true) != whole {
                reply_idle_mismatch.push(line);
            }
        }
    }
    println!(
        "\nhost replies: {} replies, {} splits\n  burst (no pause): {} differ\n  pause between:    {} differ",
        HOST_REPLIES.len(),
        reply_splits,
        reply_burst_mismatch.len(),
        reply_idle_mismatch.len()
    );

    let pct = |bad: usize| 100.0 * (splits - bad) as f64 / splits.max(1) as f64;
    println!(
        "\nsplit reads: {} sequences, {} splits\n  burst (no pause): {:.1}% identical ({} differ)\n  pause between:    {:.1}% identical ({} differ)",
        corpus.len(),
        splits,
        pct(burst_mismatch.len()),
        burst_mismatch.len(),
        pct(idle_mismatch.len()),
        idle_mismatch.len()
    );
    if let Ok(path) = std::env::var("HERDR_INPUT_CONFORMANCE_FAILURES") {
        let lines: Vec<String> = burst_mismatch
            .iter()
            .chain(&reply_burst_mismatch)
            .map(|line| format!("burst\t{line}"))
            .chain(
                idle_mismatch
                    .iter()
                    .chain(&reply_idle_mismatch)
                    .map(|line| format!("idle\t{line}")),
            )
            .collect();
        std::fs::write(path, lines.join("\n")).expect("write failures");
    }
    assert!(
        burst_mismatch.is_empty() && reply_burst_mismatch.is_empty(),
        "split reads without a pause changed the decoded input"
    );
    assert!(
        idle_mismatch.len() <= SPLIT_IDLE_MISMATCH_BASELINE,
        "split-read robustness regressed: {} > {SPLIT_IDLE_MISMATCH_BASELINE}",
        idle_mismatch.len()
    );
    assert!(
        reply_idle_mismatch.len() <= REPLY_IDLE_MISMATCH_BASELINE,
        "host-reply split robustness regressed: {} > {REPLY_IDLE_MISMATCH_BASELINE}",
        reply_idle_mismatch.len()
    );
}

#[tokio::test(flavor = "multi_thread")]
async fn mouse_transparency_conformance() {
    let report = run_mouse_conformance();
    print_report(&report);
    assert!(
        report.failures.len() <= MOUSE_FAILURES_BASELINE,
        "mouse transparency regressed: {} failures > {MOUSE_FAILURES_BASELINE}",
        report.failures.len()
    );
}

#[tokio::test(flavor = "multi_thread")]
async fn keyboard_transparency_conformance() {
    let report = run_keyboard_conformance();
    print_report(&report);
    assert!(
        report.failures.len() <= KEYBOARD_FAILURES_BASELINE,
        "keyboard transparency regressed: {} failures > {KEYBOARD_FAILURES_BASELINE}",
        report.failures.len()
    );
}
