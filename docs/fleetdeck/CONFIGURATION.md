# FleetDeck configuration

Settings FleetDeck adds to the configuration Herdr documents in
`docs/next/website/src/content/docs/configuration.mdx`. They live in the
same `config.toml`, under `~/.config/agent-fabric-fleetdeck/`.

## Socket access

FleetDeck's API socket and client socket accept only your own account. Any process running as you can still use them, including one running inside a pane, which can then read and type into every other pane. `socket_access` narrows that:

```toml
[server]
socket_access = "outside_panes"
```

- `"all"` (default): any process running as you.
- `"outside_panes"`: refuses every process running inside a FleetDeck pane, including the `agent-fabric-fleetdeck` CLI and agent integration hooks run there. Plugin actions, custom commands that run as a shell command or in a popup, plugin popups, and commands you run in an ordinary terminal still work. A custom command with `type = "pane"` opens a pane and is refused like one. Agent status in panes falls back to screen detection.
- `"client_only"`: serves only an attached FleetDeck client and FleetDeck's own server management (`agent-fabric-fleetdeck status`, `agent-fabric-fleetdeck server stop`, `agent-fabric-fleetdeck update`). Every other CLI and API command is refused, from anywhere.

Both restricted modes still answer status checks, so a client can tell whether a server is running. FleetDeck places a caller by its process tree and start-time environment, which it can read on Linux only. On other platforms the restricted modes refuse every caller except status checks.

This setting keeps processes in panes from using FleetDeck's sockets by the usual routes. It is not a security boundary between processes running as the same account. A process that clears its environment and then leaves its pane's session or outlives the pane, or anything started outside FleetDeck, is not refused. To isolate an agent, run it as another account.

An unrecognized value is enforced as `"client_only"` and reported as a configuration error. If the configuration file cannot be parsed, FleetDeck still reads this setting from it. Reloading the configuration applies a change to the running server. Connections already open that the new setting refuses, such as a client attached from a pane or an event subscription, are closed. On Windows they stay open until they reconnect. Under `"client_only"`, `agent-fabric-fleetdeck server reload-config` is refused, so reload from the client or restart the server.
