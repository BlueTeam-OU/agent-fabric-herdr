//! Who this build is: Agent Fabric FleetDeck, a fork of Herdr with its own
//! name, version line, directories and release channel. Where the inherited
//! code keeps a `HERDR_*` or `herdr-*` identifier on purpose (the pane and
//! plugin environment, plugin manifests, integration hooks), that identifier
//! is a contract with tools written for Herdr, not FleetDeck's name; the list
//! and the reasons are in `docs/fleetdeck/IDENTITY.md`.

/// The product as a person reads it.
pub(crate) const PRODUCT_NAME: &str = "Agent Fabric FleetDeck";

/// The executable, and the name commands are spelled with in help and errors.
pub(crate) const BIN_NAME: &str = env!("CARGO_PKG_NAME");

pub(crate) const REPOSITORY_URL: &str = "https://github.com/BlueTeam-OU/agent-fabric-fleetdeck";

pub(crate) const UPSTREAM_URL: &str = "https://github.com/herdrdev/herdr";

/// Set to "1" in every pane, popup and plugin process FleetDeck starts, beside
/// the inherited `HERDR_ENV=1`. `HERDR_ENV` alone means a Herdr server, or an
/// older build of this fork, started the process; FleetDeck then drops the
/// inherited pane context instead of talking to that server
/// ([`drop_foreign_pane_context`]).
pub(crate) const PANE_MARKER_ENV_VAR: &str = "AGENT_FABRIC_FLEETDECK";

/// Removes every `HERDR_*` variable when the process runs inside a pane that a
/// Herdr server, not FleetDeck, started. Those variables name that server's
/// socket, session, pane and config; honoured, they would make this binary
/// attach to, report into, or load the configuration of another product's
/// installation. Outside any pane, or inside a FleetDeck pane, nothing changes:
/// a `HERDR_*` variable set there was set for FleetDeck.
///
/// Runs first in `main`, before any thread exists, so mutating the process
/// environment cannot race a reader.
pub(crate) fn drop_foreign_pane_context() {
    let keys: Vec<std::ffi::OsString> = std::env::vars_os().map(|(key, _)| key).collect();
    for key in foreign_pane_context_keys(
        keys.iter().filter_map(|key| key.to_str()),
        std::env::var_os(crate::HERDR_ENV_VAR).as_deref(),
        std::env::var_os(PANE_MARKER_ENV_VAR).as_deref(),
    ) {
        std::env::remove_var(key);
    }
}

fn foreign_pane_context_keys<'a>(
    keys: impl Iterator<Item = &'a str>,
    herdr_env: Option<&std::ffi::OsStr>,
    fleetdeck_marker: Option<&std::ffi::OsStr>,
) -> Vec<&'a str> {
    let inside_some_pane = herdr_env.is_some_and(|value| value == crate::HERDR_ENV_VALUE);
    let inside_fleetdeck_pane =
        fleetdeck_marker.is_some_and(|value| value == crate::HERDR_ENV_VALUE);
    if !inside_some_pane || inside_fleetdeck_pane {
        return Vec::new();
    }
    keys.filter(|key| key.starts_with("HERDR_")).collect()
}

#[cfg(test)]
mod tests {
    use std::ffi::OsStr;

    use super::*;

    const KEYS: [&str; 5] = [
        "HERDR_ENV",
        "HERDR_SOCKET_PATH",
        "HERDR_PANE_ID",
        "HERDR_CONFIG_PATH",
        "PATH",
    ];

    #[test]
    fn a_herdr_pane_without_the_fleetdeck_marker_loses_every_herdr_variable() {
        let dropped = foreign_pane_context_keys(KEYS.into_iter(), Some(OsStr::new("1")), None);
        assert_eq!(
            dropped,
            [
                "HERDR_ENV",
                "HERDR_SOCKET_PATH",
                "HERDR_PANE_ID",
                "HERDR_CONFIG_PATH"
            ]
        );
    }

    #[test]
    fn a_fleetdeck_pane_keeps_its_context() {
        let dropped = foreign_pane_context_keys(
            KEYS.into_iter(),
            Some(OsStr::new("1")),
            Some(OsStr::new("1")),
        );
        assert!(dropped.is_empty());
    }

    #[test]
    fn outside_any_pane_explicit_overrides_stay() {
        let dropped = foreign_pane_context_keys(KEYS.into_iter(), None, None);
        assert!(dropped.is_empty());
    }

    #[test]
    fn the_executable_is_the_package() {
        assert_eq!(BIN_NAME, "agent-fabric-fleetdeck");
    }
}
