# Fleet Deck

The operator's console over the agent fleet, built on this herdr fork.
Each agent account gets one tab, labelled with its login, holding three
panes:

| pane | runs | for |
|---|---|---|
| **harness** (left, 65 %, focused) | `moveto <account> --wait` | one line, `<account> - Enter to activate`; Enter starts or resumes the account's session |
| **shell** (top right) | `moveto <account>` | a shell as the account |
| **status** (bottom right) | `moveto <account> --watch` | the account's status, read-only |

This directory exists only in gzapi-org's fork; upstream merges never
touch it. The contract is agent-fabric's `docs/fleet-deck/tab-states.md`
(agent-fabric#115). Its state machine is implemented in `deck_tabs.py`,
and the deck around it in `fabric_deck.py`.

```sh
fabric-deck --catalog ~/projects/agent-fabric/identities/roles/catalog.json
```

The deck runs on the operator's human login, from a terminal outside any
pane: `server.socket_access = "outside_panes"` refuses pane processes. It
stays running until ctrl-c or `kill`, and the stream child goes with it.

## Restore

When the deck starts, and whenever herdr's server comes back after being
lost or replaced, every placed account (`moveto --list`, without the
deck's own login) gets its tab:
- **The tab.** A missing tab is created. On a host's first setup the role
  catalogue's group seeds the workspace; afterwards a new account goes to
  its group's workspace if one still exists, else to `New`.
- **A milestone-1 tab** (one unlabelled pane) keeps that pane as the
  harness and gains the shell and status panes.
- **A tab split by hand** with no `harness` pane is left alone, and the
  deck says so once.
- **The shell and status panes** are started when they are at the
  operator's bare shell.
- **A harness pane with moveto running** is classified and never touched.
- **A harness pane at the operator's bare shell**, or just created, waits
  5 s for the stream, then:
  - if a session runs on the account now, it gets a plain `moveto`
    shell, so an Enter there cannot start a second session;
  - if the account's session was running before the restart and none
    runs now, it gets `--resume`;
  - otherwise, or with no fresh record within 120 s, it gets `--wait`.

## What a person sees

The deck reports each harness pane into herdr's agent panel as the agent
`claude` from the source `fabric`. herdr's default agent row shows the
agent's name, so the deck's word goes in its place, and herdr's own
`claude` comes back while a harness runs.

| state | herdr state (icon, notifications) | the row reads |
|---|---|---|
| a harness runs in the pane | the session's: `working`, `idle` or `blocked` | `claude` |
| waiting for Enter | `idle` | `dormant` |
| the account's shell after a session ended here | `idle` | `shell` |
| a `--resume` the deck started, no harness yet | `working` | `restoring` |
| a `--resume` that produced no harness | `blocked` | `failed` |
| a session runs on the account, not in this pane | `unknown` | `running elsewhere` |
| the account's record is older than two heartbeats | `unknown` | `stale` |

The same words are set as herdr state labels, for a sidebar layout that
shows `state_text`. herdr shows an `idle` the person has not looked at as
`done`, so the word is set for both. The deck's terminal prints one line
per change.

## What the deck observes, and never does

- **moveto in the pane** comes from herdr's `pane process-info`. The
  pane's foreground is moveto's `sudo … enter <dir> <title> [mode]`
  hand-off, or the operator's bare shell once moveto ended. A bare shell
  is its own foreground process group (`foreground_process_group_id ==
  shell_pid`).
- **A harness in the pane** is a `claude` process, or agent-fabric's
  `launch.py`, among the descendants of that `sudo`.
  - sudo runs the account in a pty of its own (`use_pty`), so the harness
    is never in the pane's foreground. The deck walks `/proc/<pid>/stat`
    parent links instead, and reads only `stat`, plus `cmdline` of those
    descendants.
  - This was measured live on develop-qzapp (GZCoord seq 22145); `/proc`
    is mounted without `hidepid`.
- **The account's sessions** come from `fabric-ctl all states --follow
  --json`, this host's records only. The stream is restarted after 1, 2,
  5, 10, 30, then 60 s.
- **herdr's server instance** is the pid at the socket's other end
  (`SO_PEERCRED`) plus that process's start ticks. A different or
  unreadable instance is a loss of herdr, and its next answer is a
  restore.
- **What the deck does to panes:** it starts a fixed `moveto <account>
  [--wait|--resume|--watch]` only in the operator's own bare shell. While
  moveto runs, it never types into a pane, sends a key or closes one. A
  pane a person closes stays closed until the next restore.
- **What the deck never does:** it never retries a failed `--resume`. One
  Enter in the re-armed `--wait` pane does that.

Until agent-fabric's activation PR puts `--wait`, `--watch` and
`fabric-resume`'s second-session refusal on main, `moveto --help` does not
list them. The deck then arms no pane with them, says so once, and shows
those harness panes as herdr's `unknown`.

## What the deck keeps

`$XDG_STATE_HOME/fabric-deck/before.json` (mode 0600) holds, per placed
account, whether its session was running. It is read only at a restore,
to decide `--resume`.
- **A rise** is written at once.
- **A fall** is written only once herdr has visibly stayed up. That takes
  an answer from the same server instance as the last answer before the
  fall, at least 5 s after it. A fall seen around a loss of herdr never
  settles, so a session that died with herdr is resumed.
- **A fall still pending when the deck stops** is kept with its server
  instance. At the next start it settles only if that same server is
  still running.
- **An account that leaves `moveto --list`** is dropped at the next write.

## Tests

`just fleet-deck-test` runs the state machine (`test_deck_tabs`) and the
deck against a fake herdr, a fake `/proc` and a real Unix socket
(`test_fabric_deck`), without a server.

The deck was also run against a real, isolated herdr server, with
stand-ins for `moveto` and `fabric-ctl`. The `moveto` stand-in has the
same `sudo … enter` argv shape and a pty of its own for the account's
shell. The run covered:
- restore, with `--resume` and `--wait`;
- Enter;
- a session ending;
- a deck restart that re-armed nothing;
- a herdr server restart that resumed only the session that died with
  it.

The rendered herdr client was inspected on a private X display. The real
`moveto`, `fabric-resume` and the fleet's stream have not been run with
it.
