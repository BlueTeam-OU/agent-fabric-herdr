# Agent Fabric FleetDeck

The terminal workspace the agent fleet runs in. Each agent account has
its own tab, a status for each pane, and an operator's console over the
whole fleet (`fleet-deck/`).

FleetDeck is a fork of [Herdr](https://github.com/herdrdev/herdr) by its
authors. It keeps Herdr's runtime: a background server that keeps
terminals running, workspaces with tabs and panes, recognition of coding
agents, the CLI and socket API, and plugins. On top of that it adds what
the fleet needs:

- a switch that limits the socket API to clients outside the panes;
- clipboard keys that leave every harness key to the harness;
- the Fleet Deck: one tab per agent, recovered after a restart, with
  views of the fleet;
- a sound for each agent-state transition.

FleetDeck has its own name, directories, version line and release
channel, so it runs beside a Herdr installation without touching it.

- What FleetDeck renamed, what it kept, and how to move an existing
  installation: [docs/fleetdeck/IDENTITY.md](docs/fleetdeck/IDENTITY.md)
- The fork point, the versioning policy, and how upstream changes are
  imported: [docs/fleetdeck/UPSTREAM.md](docs/fleetdeck/UPSTREAM.md)
- Settings FleetDeck adds, such as `server.socket_access`:
  [docs/fleetdeck/CONFIGURATION.md](docs/fleetdeck/CONFIGURATION.md)

## Install

FleetDeck has published no release yet. Build it from source:

```bash
git clone https://github.com/BlueTeam-OU/agent-fabric-fleetdeck
cd agent-fabric-fleetdeck
cargo build --release          # needs Zig 0.16.0 for the vendored libghostty-vt
install -m 755 target/release/agent-fabric-fleetdeck ~/.local/bin/
```

After the first release, `distribution/install.sh` installs the release
binary for your platform.

Start it where the work lives:

```bash
agent-fabric-fleetdeck
```

`ctrl+6 q` detaches (FleetDeck's prefix is ctrl+6), and
`agent-fabric-fleetdeck` attaches again. To run the fleet, see
[fleet-deck/README.md](fleet-deck/README.md).

## Docs

`docs/` holds Herdr's documentation as Herdr published it. Its commands
read `herdr`; with FleetDeck, type `agent-fabric-fleetdeck` instead.
`agent-fabric-fleetdeck --help` and `agent-fabric-fleetdeck --skill`
already use this build's names.

## Development

```bash
just test        # unit tests
just check       # formatting, tests, and maintenance checks
```

Read [`CLAUDE.md`](./CLAUDE.md) before making changes. Its upstream
sections are Herdr's rules for its own repository, and its last section
says what this fork follows.

## Licence

FleetDeck, like Herdr, is licensed under the
[Apache License 2.0](LICENSE). Herdr's authors hold the copyright of the
code inherited from it; [SPONSORS.md](./SPONSORS.md) lists Herdr's
sponsors.
