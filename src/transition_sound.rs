//! A sound per agent state transition, and per account (fork-only).
//!
//! `[ui.sound.transitions]` maps `"FROM -> TO"` over herdr's agent states
//! (`idle`, `working`, `blocked`, `unknown`, or `*` for any) to an mp3 path or
//! `"off"`; `[ui.sound.accounts."<login>"]` is the same table for a pane whose
//! `account` metadata token names that login, and wins over the global one.
//! A transition neither table names keeps upstream's two events (done,
//! request), so empty tables change nothing.
//!
//! The server decides, because only it sees every transition (upstream sends
//! the client nothing for idle -> working). It sends the decision to clients
//! as a sound label on the existing `Notify { kind: Sound }` message, and
//! each client resolves the label against its own config: no wire format
//! changes, and a client without this module ignores the label. This file
//! holds everything an upstream merge would otherwise collide with; the
//! hooks into upstream code are calls into it.

use std::collections::{BTreeMap, HashMap};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use crate::config::SoundConfig;
use crate::detect::AgentState;
use crate::layout::PaneId;
use crate::sound::Sound;

/// The pane metadata token that names the account a pane runs as. Fleet
/// Deck sets it with `herdr pane report-metadata --token account=<login>`.
pub const ACCOUNT_TOKEN: &str = "account";

/// At most one transition sound per pane in this window, so a fleet that
/// resumes at once does not repeat a pane's sound for each step it passes.
pub const PANE_SOUND_INTERVAL: Duration = Duration::from_secs(1);

/// `[ui.sound] fleet_min_interval_ms` unset: a fleet resuming at once plays
/// at most four transition sounds a second.
pub const DEFAULT_FLEET_MIN_INTERVAL_MS: u64 = 250;

const LABEL_PREFIX: &str = "transition ";
const OFF: &str = "off";

/// `"FROM -> TO"` keys to an mp3 path, relative to the config file, or "off".
pub type TransitionTable = BTreeMap<String, String>;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Side {
    Any,
    State(AgentState),
}

impl Side {
    fn matches(self, state: AgentState) -> bool {
        match self {
            Side::Any => true,
            Side::State(side) => side == state,
        }
    }
}

fn parse_state(word: &str) -> Option<AgentState> {
    match word {
        "idle" => Some(AgentState::Idle),
        "working" => Some(AgentState::Working),
        "blocked" => Some(AgentState::Blocked),
        "unknown" => Some(AgentState::Unknown),
        _ => None,
    }
}

fn state_word(state: AgentState) -> &'static str {
    match state {
        AgentState::Idle => "idle",
        AgentState::Working => "working",
        AgentState::Blocked => "blocked",
        AgentState::Unknown => "unknown",
    }
}

fn parse_side(word: &str) -> Option<Side> {
    let word = word.trim().to_ascii_lowercase();
    if word == "*" {
        return Some(Side::Any);
    }
    parse_state(&word).map(Side::State)
}

fn parse_key(key: &str) -> Result<(Side, Side), String> {
    let (from, to) = key
        .split_once("->")
        .ok_or_else(|| format!("{key:?} is not \"FROM -> TO\""))?;
    let side = |word: &str| {
        parse_side(word).ok_or_else(|| {
            format!(
                "{key:?}: {:?} is not idle, working, blocked, unknown or *",
                word.trim()
            )
        })
    };
    Ok((side(from)?, side(to)?))
}

/// How specific a key is. A named arrival beats a named departure: the
/// sound tells a person where the agent is now, so `* -> blocked` wins over
/// `idle -> *` for idle -> blocked.
fn specificity(from: Side, to: Side) -> u8 {
    u8::from(matches!(to, Side::State(_))) * 2 + u8::from(matches!(from, Side::State(_)))
}

/// The value of the most specific key in `table` matching the transition.
/// Two spellings of one key (`idle->working`, `IDLE -> working`) are equally
/// specific; the first in key order wins, and diagnostics name the second.
fn lookup(table: &TransitionTable, from: AgentState, to: AgentState) -> Option<&str> {
    let mut best: Option<(u8, &str)> = None;
    for (key, value) in table {
        let Ok((from_side, to_side)) = parse_key(key) else {
            continue;
        };
        if !(from_side.matches(from) && to_side.matches(to)) {
            continue;
        }
        let rank = specificity(from_side, to_side);
        if best.is_none_or(|(best_rank, _)| rank > best_rank) {
            best = Some((rank, value.as_str()));
        }
    }
    best.map(|(_, value)| value)
}

/// What the tables say about one transition.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Choice {
    /// Neither table names it: upstream's done/request sound plays as before.
    Unset,
    /// A table names it "off": no sound, upstream's included.
    Off,
    /// A table names a file, as written in the config.
    Play(PathBuf),
}

impl Choice {
    /// Whether this replaces the sound upstream would play for the transition.
    pub fn claims(&self) -> bool {
        !matches!(self, Choice::Unset)
    }
}

pub fn choose(
    config: &SoundConfig,
    account: Option<&str>,
    from: AgentState,
    to: AgentState,
) -> Choice {
    if from == to {
        return Choice::Unset;
    }
    let by_account = account
        .and_then(|account| config.accounts.get(account))
        .and_then(|table| lookup(table, from, to));
    match by_account.or_else(|| lookup(&config.transitions, from, to)) {
        None => Choice::Unset,
        Some(value) if value.trim().eq_ignore_ascii_case(OFF) => Choice::Off,
        Some(value) => Choice::Play(PathBuf::from(value.trim())),
    }
}

/// The transition as the server sends it to clients, in `Notify.message`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Label {
    pub from: AgentState,
    pub to: AgentState,
    pub account: Option<String>,
    /// What plays when the client's own tables do not name the transition,
    /// or its file cannot be played: upstream's sound for the transition.
    pub fallback: Option<Sound>,
}

impl Label {
    pub fn encode(&self) -> String {
        let fallback = match self.fallback {
            Some(Sound::Done) => "done",
            Some(Sound::Request) => "request",
            None => "none",
        };
        let mut label = format!(
            "{LABEL_PREFIX}{}->{} fallback={fallback}",
            state_word(self.from),
            state_word(self.to)
        );
        if let Some(account) = &self.account {
            label.push_str(" account=");
            label.push_str(account);
        }
        label
    }

    pub fn decode(message: &str) -> Option<Self> {
        let rest = message.strip_prefix(LABEL_PREFIX)?;
        let mut words = rest.split(' ');
        let (from, to) = words.next()?.split_once("->")?;
        let mut label = Label {
            from: parse_state(from)?,
            to: parse_state(to)?,
            account: None,
            fallback: None,
        };
        for word in words {
            match word.split_once('=')? {
                ("fallback", "done") => label.fallback = Some(Sound::Done),
                ("fallback", "request") => label.fallback = Some(Sound::Request),
                ("fallback", "none") => label.fallback = None,
                ("account", account) if valid_account(account) => {
                    label.account = Some(account.to_owned())
                }
                _ => return None,
            }
        }
        Some(label)
    }
}

/// A login as a label carries it: one word, so the label stays parseable.
fn valid_account(account: &str) -> bool {
    !account.is_empty()
        && account
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '_' | '-' | '.'))
}

/// The account a pane's metadata names, when it is one a label can carry.
pub fn pane_account(tokens: &HashMap<String, String>) -> Option<String> {
    tokens
        .get(ACCOUNT_TOKEN)
        .filter(|account| valid_account(account))
        .cloned()
}

/// Client side: plays a transition label against the client's own config.
/// Returns false for a message that is not a transition label.
pub fn play_label(message: &str, config: &SoundConfig) -> bool {
    let Some(playback) = playback_for_label(message, config) else {
        return false;
    };
    match playback {
        Playback::Silent => {}
        Playback::File { path, fallback } => crate::sound::play_file_or(path, fallback, config),
        Playback::BuiltIn(sound) => crate::sound::play(sound, config),
    }
    true
}

/// What a client plays for a message.
#[derive(Debug, Clone, PartialEq, Eq)]
enum Playback {
    Silent,
    /// A configured file, resolved; the built-in sound if it cannot play.
    File {
        path: PathBuf,
        fallback: Sound,
    },
    BuiltIn(Sound),
}

/// None for a message that is not a transition label.
fn playback_for_label(message: &str, config: &SoundConfig) -> Option<Playback> {
    let label = Label::decode(message)?;
    if !config.enabled {
        return Some(Playback::Silent);
    }
    Some(
        match choose(config, label.account.as_deref(), label.from, label.to) {
            Choice::Off => Playback::Silent,
            Choice::Play(path) => Playback::File {
                path: crate::config::resolve_sound_path(&path),
                fallback: label.fallback.unwrap_or(Sound::Done),
            },
            // This client's tables differ from the server's: upstream's sound.
            Choice::Unset => label.fallback.map_or(Playback::Silent, Playback::BuiltIn),
        },
    )
}

/// On the server: one transition sound per pane per `PANE_SOUND_INTERVAL`,
/// and across all panes one per `fleet_interval` (`[ui.sound]
/// fleet_min_interval_ms`; zero: no fleet limit). A sound either limit
/// drops is not counted against the other.
#[derive(Debug, Default)]
pub struct TransitionSoundLimiter {
    last: HashMap<PaneId, Instant>,
    last_any: Option<Instant>,
}

impl TransitionSoundLimiter {
    pub fn allow(&mut self, pane: PaneId, now: Instant, fleet_interval: Duration) -> bool {
        // Entries older than the window decide nothing; dropping them here
        // bounds the map by the panes that sounded within the last second.
        self.last
            .retain(|_, at| now.saturating_duration_since(*at) < PANE_SOUND_INTERVAL);
        if self.last.contains_key(&pane) {
            return false;
        }
        if self
            .last_any
            .is_some_and(|at| now.saturating_duration_since(at) < fleet_interval)
        {
            return false;
        }
        self.last.insert(pane, now);
        self.last_any = Some(now);
        true
    }
}

pub fn diagnostics(config: &SoundConfig) -> Vec<String> {
    let mut diagnostics = Vec::new();
    let tables = std::iter::once(("ui.sound.transitions".to_owned(), &config.transitions)).chain(
        config
            .accounts
            .iter()
            .map(|(account, table)| (format!("ui.sound.accounts.{account:?}"), table)),
    );
    for (field, table) in tables {
        let mut seen: Vec<((Side, Side), &String)> = Vec::new();
        for (key, value) in table {
            match parse_key(key) {
                Err(err) => diagnostics.push(format!("invalid sound transition: {field}: {err}; ignored")),
                Ok(sides) => match seen.iter().find(|(other, _)| *other == sides) {
                    Some((_, first)) => diagnostics.push(format!(
                        "duplicate sound transition: {field}: {key:?} names the same transition as {first:?}; {first:?} is used"
                    )),
                    None => seen.push((sides, key)),
                },
            }
            if value.trim().eq_ignore_ascii_case(OFF) {
                continue;
            }
            if let Some(problem) =
                file_problem(&crate::config::resolve_sound_path(Path::new(value.trim())))
            {
                diagnostics.push(format!(
                    "{problem}: {field}.{key:?} = {value}; using the built-in sound"
                ));
            }
        }
    }
    diagnostics
}

fn file_problem(resolved: &Path) -> Option<&'static str> {
    if resolved
        .extension()
        .and_then(|ext| ext.to_str())
        .is_none_or(|ext| !ext.eq_ignore_ascii_case("mp3"))
    {
        Some("unsupported sound file format (expected an mp3 file)")
    } else if !resolved.exists() {
        Some("missing sound file")
    } else if !resolved.is_file() {
        Some("invalid sound file")
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::Config;
    use AgentState::{Blocked, Idle, Unknown, Working};

    fn sound(toml: &str) -> SoundConfig {
        toml::from_str::<Config>(toml).unwrap().ui.sound
    }

    fn play(path: &str) -> Choice {
        Choice::Play(PathBuf::from(path))
    }

    #[test]
    fn keys_parse_with_any_spacing_and_case_and_a_wildcard_side() {
        assert_eq!(
            parse_key("idle -> working"),
            Ok((Side::State(Idle), Side::State(Working)))
        );
        assert_eq!(
            parse_key("IDLE->Blocked"),
            Ok((Side::State(Idle), Side::State(Blocked)))
        );
        assert_eq!(
            parse_key(" * -> blocked "),
            Ok((Side::Any, Side::State(Blocked)))
        );
        assert_eq!(
            parse_key("unknown -> *"),
            Ok((Side::State(Unknown), Side::Any))
        );
        assert!(parse_key("idle working").is_err());
        assert!(
            parse_key("idle -> done").is_err(),
            "done is a display word, not a state"
        );
        assert!(parse_key("-> idle").is_err());
    }

    #[test]
    fn the_most_specific_key_wins_and_a_named_arrival_beats_a_named_departure() {
        let config = sound(
            r#"
[ui.sound.transitions]
"* -> *" = "any.mp3"
"idle -> *" = "from-idle.mp3"
"* -> blocked" = "to-blocked.mp3"
"working -> blocked" = "exact.mp3"
"#,
        );
        assert_eq!(choose(&config, None, Working, Blocked), play("exact.mp3"));
        assert_eq!(choose(&config, None, Idle, Blocked), play("to-blocked.mp3"));
        assert_eq!(choose(&config, None, Idle, Working), play("from-idle.mp3"));
        assert_eq!(choose(&config, None, Blocked, Idle), play("any.mp3"));
        assert_eq!(
            choose(&config, None, Idle, Idle),
            Choice::Unset,
            "no transition"
        );
    }

    #[test]
    fn off_claims_the_transition_and_an_invalid_key_is_ignored() {
        let config = sound(
            r#"
[ui.sound.transitions]
"* -> blocked" = "Off"
"idle -> later" = "never.mp3"
"#,
        );
        assert_eq!(choose(&config, None, Working, Blocked), Choice::Off);
        assert!(Choice::Off.claims());
        assert_eq!(choose(&config, None, Idle, Working), Choice::Unset);
        assert!(config
            .diagnostics()
            .iter()
            .any(|diag| diag.contains("invalid sound transition") && diag.contains("later")));
    }

    #[test]
    fn empty_tables_leave_every_transition_to_upstream() {
        let config = sound("[ui.sound]\nenabled = true\n");
        assert_eq!(config, SoundConfig::default());
        for from in [Idle, Working, Blocked, Unknown] {
            for to in [Idle, Working, Blocked, Unknown] {
                let choice = choose(&config, Some("rust-ui-dev-01"), from, to);
                assert_eq!(choice, Choice::Unset);
                assert!(!choice.claims());
            }
        }
    }

    #[test]
    fn an_account_table_wins_over_the_global_one_even_when_less_specific() {
        let config = sound(
            r#"
[ui.sound.transitions]
"idle -> working" = "global.mp3"
"working -> idle" = "global-done.mp3"

[ui.sound.accounts."rust-ui-dev-01"]
"* -> *" = "account.mp3"

[ui.sound.accounts."quiet-01"]
"idle -> working" = "off"
"#,
        );
        assert_eq!(
            choose(&config, Some("rust-ui-dev-01"), Idle, Working),
            play("account.mp3")
        );
        assert_eq!(
            choose(&config, Some("quiet-01"), Idle, Working),
            Choice::Off
        );
        assert_eq!(
            choose(&config, Some("quiet-01"), Working, Idle),
            play("global-done.mp3"),
            "what the account table does not name falls to the global table"
        );
        assert_eq!(
            choose(&config, Some("other"), Idle, Working),
            play("global.mp3")
        );
        assert_eq!(choose(&config, None, Idle, Working), play("global.mp3"));
    }

    #[test]
    fn labels_round_trip_and_refuse_what_they_cannot_carry() {
        let label = Label {
            from: Idle,
            to: Working,
            account: Some("rust-ui-dev-01".into()),
            fallback: None,
        };
        assert_eq!(
            label.encode(),
            "transition idle->working fallback=none account=rust-ui-dev-01"
        );
        assert_eq!(Label::decode(&label.encode()), Some(label));
        let label = Label {
            from: Working,
            to: Blocked,
            account: None,
            fallback: Some(Sound::Request),
        };
        assert_eq!(Label::decode(&label.encode()), Some(label));
        assert_eq!(Label::decode("agent done"), None);
        assert_eq!(Label::decode("transition idle->done fallback=none"), None);
        assert_eq!(Label::decode("transition idle->working account=a b"), None);
        assert_eq!(Label::decode("transition idle->working colour=red"), None);
    }

    #[test]
    fn only_a_one_word_account_token_names_the_account() {
        let tokens = |value: &str| HashMap::from([(ACCOUNT_TOKEN.to_owned(), value.to_owned())]);
        assert_eq!(
            pane_account(&tokens("rust-ui-dev-01")),
            Some("rust-ui-dev-01".into())
        );
        assert_eq!(pane_account(&tokens("two words")), None);
        assert_eq!(pane_account(&HashMap::new()), None);
    }

    #[test]
    fn a_pane_sounds_once_a_second_and_other_panes_are_not_held() {
        let mut limiter = TransitionSoundLimiter::default();
        let start = Instant::now();
        let pane = PaneId::from_raw(1);
        let other = PaneId::from_raw(2);
        let no_fleet_limit = Duration::ZERO;
        assert!(limiter.allow(pane, start, no_fleet_limit));
        assert!(!limiter.allow(pane, start + Duration::from_millis(999), no_fleet_limit));
        assert!(limiter.allow(other, start + Duration::from_millis(999), no_fleet_limit));
        assert!(limiter.allow(pane, start + PANE_SOUND_INTERVAL, no_fleet_limit));
        assert_eq!(limiter.last.len(), 2);
        assert!(limiter.allow(other, start + Duration::from_secs(5), no_fleet_limit));
        assert_eq!(limiter.last.len(), 1, "stale entries are dropped");
    }

    #[test]
    fn across_panes_one_sound_per_fleet_interval_and_a_dropped_one_is_not_counted() {
        let mut limiter = TransitionSoundLimiter::default();
        let start = Instant::now();
        let fleet = Duration::from_millis(250);
        let [a, b, c] = [1, 2, 3].map(PaneId::from_raw);
        assert!(limiter.allow(a, start, fleet));
        assert!(!limiter.allow(b, start + Duration::from_millis(249), fleet));
        assert!(
            limiter.allow(b, start + fleet, fleet),
            "b's dropped sound did not start a pane window for b"
        );
        assert!(!limiter.allow(c, start + Duration::from_millis(400), fleet));
        assert!(limiter.allow(c, start + Duration::from_millis(500), fleet));
        assert!(
            !limiter.allow(a, start + Duration::from_millis(900), fleet),
            "the pane limit still holds past the fleet interval"
        );
    }

    #[test]
    fn a_client_resolves_a_label_against_its_own_tables() {
        let label = |from, to, fallback| {
            Label {
                from,
                to,
                account: Some(ACCOUNT.into()),
                fallback,
            }
            .encode()
        };
        const ACCOUNT: &str = "rust-ui-dev-01";
        let config = sound(
            r#"
[ui.sound.accounts."rust-ui-dev-01"]
"idle -> working" = "sounds/start.mp3"
"working -> blocked" = "off"
"#,
        );
        let root = crate::config::config_path().parent().unwrap().to_path_buf();
        assert_eq!(
            playback_for_label(&label(Idle, Working, None), &config),
            Some(Playback::File {
                path: root.join("sounds/start.mp3"),
                fallback: Sound::Done
            })
        );
        assert_eq!(
            playback_for_label(&label(Working, Blocked, Some(Sound::Request)), &config),
            Some(Playback::Silent)
        );
        assert_eq!(
            playback_for_label(&label(Blocked, Idle, Some(Sound::Done)), &config),
            Some(Playback::BuiltIn(Sound::Done)),
            "a transition this client's tables do not name plays upstream's sound"
        );
        assert_eq!(
            playback_for_label(&label(Idle, Unknown, None), &config),
            Some(Playback::Silent)
        );
        let disabled = sound("[ui.sound]\nenabled = false\n");
        assert_eq!(
            playback_for_label(&label(Blocked, Idle, Some(Sound::Done)), &disabled),
            Some(Playback::Silent)
        );
        assert_eq!(playback_for_label("agent done", &config), None);
    }

    #[test]
    fn a_missing_transition_file_is_named_in_diagnostics() {
        let config = sound(
            r#"
[ui.sound.accounts."rust-ui-dev-01"]
"idle -> working" = "sounds/missing.mp3"
"#,
        );
        assert!(config
            .diagnostics()
            .iter()
            .any(|diag| diag.contains("missing sound file")
                && diag.contains("rust-ui-dev-01")
                && diag.contains("idle -> working")));
    }
}
