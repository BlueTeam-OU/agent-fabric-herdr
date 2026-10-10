---
role: "rust-ui-dev"
class: solution
topic: "moveto-sudo-own-pty"
description: "why herdr process-info on a moveto pane never shows claude — sudo use_pty puts the account on its own pty"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: herdr
    working_copy: herdr
derived_from:
  - 03589eede84fd4c3
---

## why herdr process-info on a moveto pane never shows claude — sudo use_pty puts the account on its own pty

moveto ends with `exec sudo -n -u <acct> -H /usr/local/share/moveto/enter <dir> <title>`. sudo 1.9.17p2 on develop-qzapp runs it under use_pty (the default since 1.9.14): the pane's tty foreground group is the outer root-owned sudo alone, and the account's bash, launch.py and claude sit on a new pty in a new session. herdr's `pane process-info` reads the pane tty's foreground group (tcgetpgrp, src/platform/linux.rs:663), so it shows only that sudo argv — moveto's mode (last argument) is readable there, the harness never is.

To tell whether the harness runs in a pane, walk /proc/<pid>/stat ppid links down from the foreground sudo (/proc has no hidepid here, so the operator's login can read them). Measured live with `ps --forest` on 2026-10-08; raised to fabric-coordinator as OBSERVATION 01a11ab5 against agent-fabric#115's tab-states.md.

Related: [[herdr-restart-loses-moveto-agents]], [[herdr-socket-access-design]].

*References: herdr-restart-loses-moveto-agents, herdr-socket-access-design*

*Observed 2026-10-08 (rust-ui-dev)*
