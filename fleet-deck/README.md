# Fleet Deck

The operator's console over the agent fleet, built on this herdr fork:
one tab per agent account, each entered with `moveto <account>`. This
directory exists only in gzapi-org's fork; upstream merges never touch it.

## Recovery

When herdr's server stops (`herdr server stop`, a reboot, a crash), every
pane process dies. The layout and the tab labels come back, but every
account tab is a bare operator shell. `fabric-deck` brings each one back:

1. It reads the accounts (`moveto --list`, without the deck's own login)
   and finds each account's tab by its label, in any workspace.
2. An account with no tab gets one. On a host's first setup the role
   catalogue's group seeds the workspace (`--catalog`). Afterwards the
   operator's layout is the truth: a new account goes to its group's
   workspace if one still exists, else to `New`.
3. A tab that is a bare shell is re-entered with
   `moveto <account> --resume` (plain `moveto <account>` until moveto has
   the flag). A tab already running its session is left alone.
4. It follows `fabric-ctl all states --follow --json` and prints one line
   per re-entered account: `restoring`, `resumed`, `fresh`, `failed` (with
   the pane's last lines) or `stale`. It waits up to `RESTORE_WAIT_S`
   (120 s) for each account.

The contract is agent-fabric's `docs/fleet-deck/session-recovery.md`. In
short:
- the control plane owns which session belongs to which account;
- herdr keeps only the layout, and the tab label is the mapping;
- the deck holds no session ids;
- the deck runs on the operator's human login, from a terminal outside
  any pane, because `server.socket_access = "outside_panes"` refuses pane
  processes.

```sh
fabric-deck --dry-run                       # the plan, changing nothing
fabric-deck --catalog ~/projects/agent-fabric/identities/roles/catalog.json
```

## Agent status in herdr

`fabric-deck --watch` keeps herdr's agent panel in step with the fleet, so
an account tab no longer reads "agent status unknown". It follows
`fabric-ctl all states --follow --json` for this host and reports each
account's state into its tab's pane as the agent `claude` from the source
`fabric`:
- `working`, `idle` and `blocked` are reported as they are;
- `none` (no session) releases the agent;
- anything else, the stream's stale rows included, is reported `unknown`.

It reports only on a change: the stream's ten-minute heartbeat sends
nothing. A split account tab is not reported into. When the stream exits,
the deck restarts it after 1, 2, 5, 10, 30, then 60 s, and from 1 s again
once a stream has run a minute. `kill` and ctrl-c stop it cleanly, the
stream child with it.

Reports carry no `--seq`. herdr refuses a sequence number that is not
above the last one from the same source, and a restarted deck would start
again from zero; with none ever sent, every report from `fabric` applies.

## How a bare tab is recognised

herdr's `pane process-info` reports a pane's `shell_pid` and its
`foreground_process_group_id`:
- **A shell waiting at its prompt** is its own foreground process group:
  `foreground_process_group_id == shell_pid`. Measured on herdr 0.9.3
  (fork 99d4887a): shell 1383031, foreground group 1383031.
- **A pane running a command** (a `moveto` session puts `sudo` in the
  foreground) is not: shell 1383065, foreground group 1383285 (`sleep`).

Process names and command lines are world-readable, so the test works
across logins and needs no change to herdr.

## Tests

`just fleet-deck-test` runs the planning core and the status rules
without a server. The recovery loop was exercised against a real,
isolated herdr server, with stand-ins for `moveto` and `fabric-ctl`.
