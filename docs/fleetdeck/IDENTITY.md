# FleetDeck's identity

What FleetDeck renamed when it stopped being "a herdr fork", what it kept
from Herdr on purpose, and how an existing installation moves over. The
versioning policy and the fork's provenance are in
[UPSTREAM.md](UPSTREAM.md).

## What is FleetDeck's

| | Herdr (and this fork before 0.10.0) | FleetDeck |
|---|---|---|
| Product | Herdr | Agent Fabric FleetDeck |
| Package, executable | `herdr` | `agent-fabric-fleetdeck` |
| Version | 0.9.3 (inherited) | 0.10.0, its own line |
| Config, sessions, sockets, logs (`$XDG_CONFIG_HOME` or `~/.config`, `$XDG_STATE_HOME`) | `herdr/`, `herdr-dev/` | `agent-fabric-fleetdeck/`, `agent-fabric-fleetdeck-dev/` |
| Default worktree directory | `~/.herdr/worktrees` | `~/.agent-fabric-fleetdeck/worktrees` |
| Update manifests | `herdr.dev/latest.json`, `/preview.json` | `distribution/latest.json`, `distribution/preview.json` on this repository's `master`, read through `raw.githubusercontent.com` |
| Agent-detection catalog | `herdr.dev/agent-detection/` | `distribution/agent-detection/` on this repository's `master` |
| Release assets | `herdr-<os>-<arch>`, `herdr-windows-x86_64.zip` (holding `herdr.exe`) | `agent-fabric-fleetdeck-<os>-<arch>`, `agent-fabric-fleetdeck-windows-x86_64.zip` (holding `agent-fabric-fleetdeck.exe`) |
| Release tags | Herdr's `v*`, `preview-*` (kept, never released here) | `v<version>` and `preview-<date>-<sha>` whose source is the `agent-fabric-fleetdeck` package |
| Installer variables | `HERDR_INSTALL_DIR`, `HERDR_HOME`, `HERDR_CHANNEL`, `HERDR_MANIFEST_URL`, `HERDR_EXPECTED_BUILD_ID` | `AGENT_FABRIC_FLEETDECK_INSTALL_DIR`, `…_HOME`, `…_CHANNEL`, `…_MANIFEST_URL`, `…_EXPECTED_BUILD_ID` |
| Windows install | `%LOCALAPPDATA%\Programs\Herdr`, `~\.herdr` | `%LOCALAPPDATA%\Programs\FleetDeck`, `~\.agent-fabric-fleetdeck` |
| Remote (`--remote`) binary | `herdr`, installed to `~/.local/bin/herdr` | `agent-fabric-fleetdeck`, installed to `~/.local/bin/agent-fabric-fleetdeck` |
| Nix flake output | `herdr` | `agent-fabric-fleetdeck` |
| Log target (`HERDR_LOG` filter) | `herdr=debug` | `agent_fabric_fleetdeck=debug` (the crate's name; the default is `=info`) |
| Windows notification identity | `Herdr.Desktop` and its activator CLSID | `AgentFabric.FleetDeck` with its own CLSID |

Help, usage lines, errors and notices name the command
`agent-fabric-fleetdeck` and the product FleetDeck. `--version` prints
`agent-fabric-fleetdeck <version>`. `--skill` prints Herdr's skill file
with every command spelled `agent-fabric-fleetdeck`.

## FleetDeck never talks to a Herdr installation

- **Separate directories.** FleetDeck reads no Herdr config, writes no
  Herdr session, and binds or connects to no Herdr socket by default. Both
  products can run side by side.
- **A Herdr pane's context is dropped.** Every process a FleetDeck server
  starts (pane, popup, plugin) carries `AGENT_FABRIC_FLEETDECK=1` next to
  the inherited `HERDR_ENV=1`. If FleetDeck starts with `HERDR_ENV=1` but
  without that marker, it is inside a pane that Herdr, or this fork before
  0.10.0, started. It then removes every `HERDR_*` variable before doing
  anything (`src/identity.rs`, `drop_foreign_pane_context`). So it does not
  attach to that server, report into its panes, or load the config file it
  names. Outside any pane, a `HERDR_*` variable you set yourself, such as
  `HERDR_SOCKET_PATH`, still applies. The fleet deck follows the same rule
  (`fleet-deck/fabric_deck.py`, `fleetdeck_env`).
- **No Herdr binaries.** The updater, the installers and `--remote` fetch
  only FleetDeck's manifests and assets. The release tooling refuses to
  publish Herdr's source (UPSTREAM.md, "What keeps Herdr's tags out").
- **No `herdr` alias.** FleetDeck installs no `herdr` command. On a host
  that also has Herdr, an alias would hide one product behind the other's
  name.

## Kept from Herdr on purpose

| Kept | Why |
|---|---|
| `HERDR_*` variables in panes, popups, plugins and hooks (`HERDR_ENV`, `HERDR_SOCKET_PATH`, `HERDR_PANE_ID`, `HERDR_BIN_PATH`, `HERDR_PLUGIN_*`, …) and the user-set overrides (`HERDR_CONFIG_PATH`, `HERDR_SESSION`, `HERDR_LOG`, …) | They are the interface that integration hooks, plugins and scripts written for Herdr read. FleetDeck tells its own panes apart with `AGENT_FABRIC_FLEETDECK`, and does not rename the 90-odd variables. |
| Plugin manifests `herdr-plugin.toml`, `min_herdr_version` | The plugin format. A plugin written for Herdr installs unchanged. `min_herdr_version` is compared with FleetDeck's version, so it is only a rough guide (known limit below). |
| Integration hook files (`herdr-agent-state.*`), `HERDR_INTEGRATION_VERSION`, report sources like `herdr:devin` | The hook protocol. Each hook calls back through `HERDR_BIN_PATH` and `HERDR_SOCKET_PATH`, so it reaches the server that started the pane, whichever product that is. `agent-fabric-fleetdeck integration install <agent>` writes to the same file names Herdr uses. It is an explicit command, and it replaces a Herdr-installed hook with an equivalent one. |
| File names inside FleetDeck's own directories: `herdr.sock`, `herdr-client.sock`, `herdr-server.log`, `herdr-client.log` | They are already separated by the directory. Renaming them would break nothing and would gain nothing. |
| Config keys and values (`[ui.toast.herdr]`, right-click target `herdr`) | Config compatibility. A Herdr `config.toml` is valid FleetDeck config. |
| Build-time `HERDR_BUILD_CHANNEL`, `HERDR_BUILD_ID`, `HERDR_BUILD_COMMIT`; test and debug variables | Internal to the build and the tests. No person sets them. |
| `skills/herdr/SKILL.md`, `docs/next/`, `docs/preview/`, `docs/versions/`, `CHANGELOG.md`, `README.zh-CN.md`, `AGENTS.md`, `CONTRIBUTING.md` | Herdr's documentation and history. They describe Herdr, which is why the command is rewritten at print time and this file exists. Keeping them verbatim keeps upstream imports small. |
| The Homebrew and mise detection in `src/update.rs` | It only matches a binary named `herdr` in a Homebrew Cellar or a mise install. FleetDeck has no formula or mise backend, so a FleetDeck binary never matches and the code is inert. No FleetDeck formula is implied. |
| `vendor/`, `crates/ghostty-vt`, copyright and licence notices | Third-party and upstream attribution. |
| `.github/workflows/pr-gate.yml`, `label-next-release-issues.yml`, `website-deploy.yml` | Herdr's contributor gate, issue bot and website deploy. They run only in `herdrdev/herdr` and are inert here; FleetDeck has none of the three. |

## Moving an existing installation

The fork ran as `herdr`, and it still does until FleetDeck is installed.
Nothing is moved for you. Do these steps once, as the login that runs it:

1. **Install `agent-fabric-fleetdeck`.** Before FleetDeck's first release,
   build it (`cargo build --release`) and put
   `target/release/agent-fabric-fleetdeck` on `PATH`. After the first
   release, the installer does it
   (`distribution/install.sh`).
2. **Carry the config over, if you want it:**

   ```sh
   mkdir -p ~/.config/agent-fabric-fleetdeck
   cp ~/.config/herdr/config.toml ~/.config/agent-fabric-fleetdeck/config.toml
   ```

   To keep worktrees where they were, add `directory = "~/.herdr/worktrees"`
   under `[worktrees]`.
3. **Link plugins again.** For example, for the fleet views:
   `agent-fabric-fleetdeck plugin link <checkout>/fleet-deck`.
4. **Start FleetDeck.** `fleet-deck` starts `agent-fabric-fleetdeck`'s
   server and rebuilds the agent tabs. A `herdr` server that is still
   running keeps its panes until you stop it with `herdr server stop`.
   The two do not see each other.
5. **Rename the variables in your own scripts.** Installer variables are
   `AGENT_FABRIC_FLEETDECK_*` (table above). A script that runs `herdr …`
   against the fork now runs `agent-fabric-fleetdeck …`.

Sessions are not migrated. Copying `session.json` across is possible while
no server runs, but the fleet deck rebuilds its tabs anyway.

## Known limits

- **Plugin version gates** (`min_herdr_version`) compare against
  FleetDeck's version. A plugin that needs a Herdr feature FleetDeck has not
  imported can pass the gate.
- **Windows** builds, the PowerShell installer and the Windows packaging
  were renamed consistently, but none of them has been run (no Windows
  host here). Before a release ships Windows assets, they must be checked
  on Windows.
- **Herdr's documentation** in `docs/` still says `herdr`.

## Setup that is not in the repository

- **Rename the hosted repository** from `BlueTeam-OU/agent-fabric-herdr`
  to `BlueTeam-OU/agent-fabric-fleetdeck`. Until then:
  - the update checks and installers point at a repository name that does
    not exist yet, and fail (the updater logs it and carries on);
  - the release and preview workflows, which are guarded to the new name,
    do not run.

  After the rename, update each clone's remote with
  `git remote set-url origin git@github.com:BlueTeam-OU/agent-fabric-fleetdeck.git`.
- **Secrets**:
  - `FLEETDECK_PUBLISH_TOKEN` lets the preview workflow push
    `distribution/preview.json` and `docs/preview` to `master`.
  - `RELEASE_DEPLOY_KEY` is a deploy key with write access, which lets the
    release workflow push `distribution/latest.json`.
- **Repository settings**:
  - a tag ruleset that lets only admins create, move or delete `v*` and
    `preview-*` tags;
  - immutable releases (`scripts/release.py` refuses a preview release
    that is not immutable);
  - admin permission for whoever pushes a release tag.
- **Nothing is published yet.** No tag was pushed, no release created, and
  nothing deployed.
