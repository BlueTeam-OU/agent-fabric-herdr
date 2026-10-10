---
role: "rust-ui-dev"
class: solution
topic: "herdr-host-toolchain"
description: "What building and checking the herdr fork needs on develop-qzapp beyond cargo, and which test failures are host artefacts"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "rust-ui-dev-01"
    host: "develop-qzapp"
    project: herdr
    working_copy: herdr
derived_from:
  - 3e02d29b970bf3c8
---

## What building and checking the herdr fork needs on develop-qzapp beyond cargo, and which test failures are host artefacts

The herdr fork (gzapi-org/herdr, clone ~/projects/herdr) builds only with Zig 0.16.0 for the vendored
libghostty-vt; on this host it lives in ~/.local/opt/zig-x86_64-linux-0.16.0 (sha256 from
ziglang.org's index), linked as ~/.local/bin/zig. Rust 1.96.1 comes from rust-toolchain.toml via
rustup (~/.cargo/bin, not on the default PATH: prefix PATH=$HOME/.cargo/bin). `just` and
`cargo-nextest` are cargo-installed; `bun` 1.3.14 (the CI pin) is npm-installed under
~/.local/opt/bun. Established 2026-10-07.

- **`just check` cannot run whole here.** Its Windows cross-lint needs the Windows SDK, which
  requires accepting Microsoft's licence; that acceptance is not this agent's to give. Run
  `just ci` and the bun suites instead, and say the Windows stage did not run.
- **The account's `tag.gpgsign=true` breaks one test.** A plain `git tag` then demands a message,
  so `plugin_install_list_uninstall_offline_cli_smoke_test` fails. Run nextest with
  `GIT_CONFIG_GLOBAL=/dev/null`.
- **Host flakes on the unchanged base.** `server_survives_hangup_and_logs_why_it_stops` fails
  about 3 runs in 5 here even on the unchanged base. `observer_write_timeout_resets_when_sending_makes_progress`
  and `foreground_job_detects_shell_running_command` flake only under full parallel load.
- **Socket paths must be short.** Smoke tests need sockets under /run/user/<uid>/…, because the
  scratchpad path exceeds the Unix socket path limit.
- **Clipboard smoke runs on a private X server.** Use `Xvfb :87` (DISPLAY=:87), never the
  operator's :0. Set `onboarding = false` in the test config, or the onboarding overlay eats the
  first keys.
- **`gh` must default to the fork.** In this clone `gh repo set-default` had been herdrdev/herdr
  (upstream), and agent-fabric's runtime/github tools followed it: a review landed on upstream
  herdrdev/herdr#3 on 2026-10-07. Keep `gh repo set-default gzapi-org/herdr`. fabric-coordinator
  fixed the tools to resolve the repository from origin (ae2137db, in review then).
- **No strace or tmux until the next fleet reboot (2026-10-09).** The owner put both in the
  template VM (devex-tooling 01a1206c); until the AppVM restarts, `dnf download --disablerepo='qubes*'
  strace` and `rpm2cpio | cpio` into the scratchpad gives a signature-checked copy (the qubes repo's
  metadata fails its GPG check). A dnf install in the AppVM itself is lost at restart.
- **nextest's `-j` is `--test-threads`**; limit the build with `CARGO_BUILD_JOBS`. Bare `rustfmt`
  ignores the project's settings and reformats other files: use `cargo fmt`.
- **Pushing needs gh's credential helper.** Git has none configured, so push with
  `git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push`.

See [[herdr-socket-access-design]].

*References: herdr-socket-access-design*

*Observed 2026-10-07 (rust-ui-dev)*
