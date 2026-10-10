//! gzapi-org's fork: herdr keeps its prefix and nothing a coding-agent harness
//! uses. Every pane in the Fleet Deck runs a harness, so a key herdr takes is a
//! key the agent loses.
//!
//! The lists below are each harness's default bindings as checked on
//! 2026-10-10. A harness that gains a binding on the prefix shows up here only
//! when its list is refreshed: re-check them when a harness's keymap changes.

use super::input_conformance::{HerdrPath, HostProfile};
use super::*;

use crate::config::parse_key_combo;
use crate::input::resolve_direct_binding;

/// Claude Code's default keybindings, every context, chords by their first
/// key (code.claude.com/docs/en/keybindings), and its reserved keys.
const CLAUDE_CODE: &[&str] = &[
    "ctrl+b",
    "ctrl+c",
    "ctrl+d",
    "ctrl+e",
    "ctrl+f",
    "ctrl+g",
    "ctrl+h",
    "ctrl+i",
    "ctrl+j",
    "ctrl+l",
    "ctrl+m",
    "ctrl+n",
    "ctrl+o",
    "ctrl+p",
    "ctrl+r",
    "ctrl+s",
    "ctrl+t",
    "ctrl+v",
    "ctrl+x",
    "ctrl+_",
    "ctrl+[",
    "ctrl+enter",
    "ctrl+up",
    "ctrl+down",
    "ctrl+home",
    "ctrl+end",
    "ctrl+shift+c",
    "alt+p",
    "alt+o",
    "alt+t",
    "alt+m",
    "alt+v",
    "alt+up",
    "alt+down",
    "shift+tab",
    "shift+space",
    "esc",
    "enter",
    "tab",
    "space",
    "backspace",
    "delete",
    "up",
    "down",
    "left",
    "right",
    "pageup",
    "pagedown",
    "home",
    "end",
];

/// Codex CLI's built-in TUI keymap (openai/codex codex-rs/tui/src/keymap.rs at
/// 806d9732, `built_in_defaults`), chords by their first key.
const CODEX: &[&str] = &[
    "ctrl+a",
    "ctrl+b",
    "ctrl+c",
    "ctrl+d",
    "ctrl+e",
    "ctrl+f",
    "ctrl+g",
    "ctrl+h",
    "ctrl+j",
    "ctrl+k",
    "ctrl+l",
    "ctrl+m",
    "ctrl+n",
    "ctrl+o",
    "ctrl+p",
    "ctrl+q",
    "ctrl+r",
    "ctrl+s",
    "ctrl+t",
    "ctrl+u",
    "ctrl+v",
    "ctrl+w",
    "ctrl+y",
    "ctrl+z",
    "ctrl+]",
    "ctrl+/",
    "ctrl+7",
    "ctrl+backspace",
    "ctrl+delete",
    "ctrl+enter",
    "ctrl+alt+v",
    "alt+b",
    "alt+d",
    "alt+f",
    "alt+r",
    "alt+,",
    "alt+.",
    "alt+backspace",
    "alt+delete",
    "alt+enter",
    "alt+up",
    "alt+down",
    "alt+left",
    "alt+right",
    "shift+tab",
    "shift+enter",
    "esc",
    "f2",
    "f3",
    "f4",
    "f5",
    "f6",
    "f7",
    "f8",
    "f9",
    "f10",
    "f12",
];

/// A plain shell: bash's default emacs keymap (`bind -p`, readline 8) and the
/// tty's control characters (`stty -a`: intr, quit, susp, eof, kill, werase,
/// rprnt, lnext, discard, start, stop).
const SHELL: &[&str] = &[
    "ctrl+space",
    "ctrl+a",
    "ctrl+b",
    "ctrl+c",
    "ctrl+d",
    "ctrl+e",
    "ctrl+f",
    "ctrl+g",
    "ctrl+h",
    "ctrl+i",
    "ctrl+j",
    "ctrl+k",
    "ctrl+l",
    "ctrl+m",
    "ctrl+n",
    "ctrl+o",
    "ctrl+p",
    "ctrl+q",
    "ctrl+r",
    "ctrl+s",
    "ctrl+t",
    "ctrl+u",
    "ctrl+v",
    "ctrl+w",
    "ctrl+x",
    "ctrl+y",
    "ctrl+z",
    "ctrl+\\",
    "ctrl+]",
    "ctrl+_",
    "alt+b",
    "alt+c",
    "alt+d",
    "alt+f",
    "alt+l",
    "alt+n",
    "alt+p",
    "alt+r",
    "alt+t",
    "alt+u",
    "alt+y",
    "alt+.",
    "alt+_",
    "alt+<",
    "alt+>",
    "alt+?",
    "alt+backspace",
    "esc",
];

const HARNESSES: &[(&str, &[&str])] = &[
    ("Claude Code", CLAUDE_CODE),
    ("Codex", CODEX),
    ("shell", SHELL),
];

/// The operator's Fleet Deck keys (fleet-deck/README.md, "Views").
const FLEET_DECK_KEYS: &str = r#"
[[keys.command]]
key = "prefix+f"
type = "plugin_action"
command = "fabric.fleet.board"

[[keys.command]]
key = "prefix+a"
type = "plugin_action"
command = "fabric.fleet.agent"

[[keys.command]]
key = "prefix+p"
type = "plugin_action"
command = "fabric.fleet.prs"
"#;

fn harness_key(label: &str) -> crate::input::TerminalKey {
    // herdr's binding syntax has no name for these keys, so no binding can
    // take them; they are still checked against the prefix.
    let (mods, name) = label.rsplit_once('+').unwrap_or(("", label));
    let named = match name {
        "home" => Some(KeyCode::Home),
        "end" => Some(KeyCode::End),
        "pageup" => Some(KeyCode::PageUp),
        "pagedown" => Some(KeyCode::PageDown),
        "delete" => Some(KeyCode::Delete),
        _ => None,
    };
    let (code, modifiers) = match named {
        Some(code) if mods.is_empty() => (code, KeyModifiers::empty()),
        Some(code) => (
            code,
            parse_key_combo(&format!("{mods}+a"))
                .expect("modifiers parse")
                .1,
        ),
        None => {
            parse_key_combo(label).unwrap_or_else(|| panic!("harness key {label:?} must parse"))
        }
    };
    crate::input::TerminalKey::new(code, modifiers)
}

fn assert_no_harness_key_is_taken(config: &Config) {
    let shell = ClientShellConfig::from_config(config);
    for (harness, labels) in HARNESSES {
        for label in *labels {
            let key = harness_key(label);
            assert!(
                !shell.keybinds.matches_prefix(&key),
                "{harness}'s {label} is herdr's prefix"
            );
            assert!(
                resolve_direct_binding(&shell.keybinds.keybinds, &key).is_none(),
                "{harness}'s {label} is a herdr binding outside the prefix"
            );
        }
    }
}

#[test]
fn the_default_prefix_and_bindings_are_no_harness_key() {
    assert_no_harness_key_is_taken(&Config::default());
    // Every other default binding is prefix+X, so it is reached only through
    // the prefix and never seen by a harness.
    let shell = ClientShellConfig::from_config(&Config::default());
    assert_eq!(
        shell.keybinds.prefix,
        vec![(KeyCode::Char('6'), KeyModifiers::CONTROL)]
    );
}

#[test]
fn the_fleet_deck_keys_are_no_harness_key() {
    let config: Config = toml::from_str(FLEET_DECK_KEYS).expect("the README's keys parse");
    assert!(config.collect_diagnostics().is_empty());
    assert_no_harness_key_is_taken(&config);
}

/// What a harness types, as each host sends it: (name, legacy host bytes,
/// kitty host bytes under disambiguate). The pane runs a program that asked
/// for nothing (legacy) or for disambiguate (kitty), as Claude Code and Codex do.
const TYPED: &[(&str, &[u8], &[u8])] = &[
    ("ctrl+c", b"\x03", b"\x1b[99;5u"),
    ("ctrl+d", b"\x04", b"\x1b[100;5u"),
    ("ctrl+z", b"\x1a", b"\x1b[122;5u"),
    ("ctrl+r", b"\x12", b"\x1b[114;5u"),
    ("ctrl+b", b"\x02", b"\x1b[98;5u"),
    ("ctrl+a", b"\x01", b"\x1b[97;5u"),
    ("ctrl+x", b"\x18", b"\x1b[120;5u"),
    ("ctrl+g", b"\x07", b"\x1b[103;5u"),
    ("ctrl+o", b"\x0f", b"\x1b[111;5u"),
    ("ctrl+t", b"\x14", b"\x1b[116;5u"),
    ("ctrl+s", b"\x13", b"\x1b[115;5u"),
    ("ctrl+q", b"\x11", b"\x1b[113;5u"),
    ("ctrl+\\", b"\x1c", b"\x1b[92;5u"),
    ("ctrl+]", b"\x1d", b"\x1b[93;5u"),
    ("ctrl+_", b"\x1f", b"\x1b[95;5u"),
    ("esc", b"\x1b", b"\x1b[27u"),
    ("alt+b", b"\x1bb", b"\x1b[98;3u"),
    ("alt+p", b"\x1bp", b"\x1b[112;3u"),
    ("alt+.", b"\x1b.", b"\x1b[46;3u"),
    ("shift+tab", b"\x1b[Z", b"\x1b[9;2u"),
    ("ctrl+left", b"\x1b[1;5D", b"\x1b[1;5D"),
    ("shift+up", b"\x1b[1;2A", b"\x1b[1;2A"),
    ("alt+up", b"\x1b[1;3A", b"\x1b[1;3A"),
    ("f2", b"\x1bOQ", b"\x1b[Q"),
    ("f12", b"\x1b[24~", b"\x1b[24~"),
];

fn deck_path(host: HostProfile) -> HerdrPath {
    let app = match host {
        HostProfile::Kitty => b"\x1b[>1u".as_slice(),
        HostProfile::Legacy => b"".as_slice(),
    };
    let mut path = HerdrPath::new(host, app);
    // No selection and no clipboard text: ctrl+c and ctrl+v are the pane's.
    path.state.read_clipboard_text = || None;
    path
}

fn assert_typed_keys_reach_the_pane(host: HostProfile) {
    let mut path = deck_path(host);
    for (name, legacy, kitty) in TYPED {
        let bytes = if host == HostProfile::Kitty {
            kitty
        } else {
            legacy
        };
        assert_eq!(
            path.feed(bytes).as_deref(),
            Some(*bytes),
            "{name} must reach the pane byte for byte ({})",
            host.name()
        );
    }
}

#[cfg(unix)]
#[tokio::test(flavor = "multi_thread")]
async fn harness_keys_reach_the_pane_byte_for_byte_from_a_legacy_host() {
    assert_typed_keys_reach_the_pane(HostProfile::Legacy);
}

#[cfg(unix)]
#[tokio::test(flavor = "multi_thread")]
async fn harness_keys_reach_the_pane_byte_for_byte_from_a_kitty_host() {
    assert_typed_keys_reach_the_pane(HostProfile::Kitty);
}

#[cfg(unix)]
#[tokio::test(flavor = "multi_thread")]
async fn only_the_prefix_is_kept_and_a_doubled_prefix_reaches_the_pane() {
    for (host, prefix) in [
        (HostProfile::Legacy, b"\x1e".as_slice()),
        (HostProfile::Kitty, b"\x1b[54;5u".as_slice()),
    ] {
        let mut path = deck_path(host);
        assert_eq!(
            path.feed(prefix),
            None,
            "the prefix is herdr's ({})",
            host.name()
        );
        assert_eq!(
            path.feed(prefix).as_deref(),
            Some(prefix),
            "prefix twice sends the prefix to the pane ({})",
            host.name()
        );
        assert_eq!(path.feed(b"x").as_deref(), Some(b"x".as_slice()));
    }
}

#[test]
fn the_check_refuses_upstreams_ctrl_b_prefix() {
    let config: Config = toml::from_str("[keys]\nprefix = \"ctrl+b\"\n").expect("parses");
    let caught = std::panic::catch_unwind(|| assert_no_harness_key_is_taken(&config));
    assert!(
        caught.is_err(),
        "ctrl+b is Claude Code's, Codex's and readline's"
    );
}
