# Upstream provenance and versioning

Agent Fabric FleetDeck (`agent-fabric-fleetdeck`,
<https://github.com/BlueTeam-OU/agent-fabric-fleetdeck>) is a fork of
Herdr, <https://github.com/herdrdev/herdr>, under the same Apache-2.0
licence. Herdr's history and tags are kept in this repository; FleetDeck's
own identity and version line start at the fork.

## The fork point

| | |
|---|---|
| Upstream commit | `3d9d2b18dab139ba226ebc5a1c9a9f2c9c3ee4df` (herdrdev/herdr `master`, 2026-10-06, "fix: keep the server alive when thread spawns fail (#4958)") |
| Inherited package version | `0.9.3` |
| Upstream release it contains | v0.9.3's source, plus 46 later commits that Herdr had not released |

How this was established, from the repository alone:

- `0bc73518`, the first fork commit (2026-10-06), has a single parent,
  `3d9d2b18`, which is on `upstream/master`.
- At `3d9d2b18`, `Cargo.toml` says `version = "0.9.3"` and
  `distribution/latest.json` names v0.9.3 as Herdr's published stable
  release.
- The tag `v0.9.3` (`7b116c05`) is **not** an ancestor of the fork point.
  Herdr promotes a stable release from a preview on a side commit and
  applies only the release metadata back to `master` (`f9a99bd2`,
  "release: synchronize metadata for v0.9.3"). v0.9.3 was promoted from
  `preview-2026-09-29-9dc3a1df2b56`, and the fork point is 46 commits after
  that preview on `master`
  (`git describe --tags 3d9d2b18` gives
  `preview-2026-09-29-9dc3a1df2b56-46-g3d9d2b18`).
- The merge base of `origin/master` and `upstream/master` today is
  `2563803d`, not the fork point: it moved with the sync recorded below.
  It is the newest upstream commit present, not where the fork began.

So the fork began from Herdr's unreleased `master` carrying version 0.9.3,
not from the v0.9.3 release commit. 0.9.3 is the inherited version
baseline. The source is "0.9.3 plus 46 upstream commits".

## Versioning policy

FleetDeck has its own [Semantic Versioning](https://semver.org) line. The
root `Cargo.toml` `[package] version` is the only source; `Cargo.lock`'s
root package, the release tag `v<version>`, and the version the binary
prints (`agent-fabric-fleetdeck --version`) must agree with it.
`scripts/release.py` checks this before anything is published.

- **PATCH** for fixes that change no public contract.
- **MINOR** for new features. While FleetDeck is below 1.0.0, a MINOR
  increment also carries any incompatible change, and its release notes
  name each one and its migration.
- **MAJOR**, from 1.0.0 on, for an incompatible change to a public
  contract. Public contracts include the CLI, config file, socket API, plugin
  interface, environment variables, paths, and the update and release channel.
- A release takes the increment its **combined** impact on FleetDeck users
  calls for: the largest of its changes decides.
- **Imported upstream changes follow the same rule.** A Herdr fix imported
  alone is a FleetDeck PATCH; a Herdr feature is a FleetDeck MINOR. Herdr's
  version numbers never set FleetDeck's, and a FleetDeck version never
  carries an upstream suffix (no `0.10.0+herdr.0.9.4`).
- **Product version is separate from the other versions.**
  `PROTOCOL_VERSION` (`src/protocol/wire.rs`),
  `ENDPOINT_PROTOCOL_GENERATION` (`src/protocol/endpoint.rs`), persisted
  session schema versions, integration asset versions and plugin manifest
  versions change only by their own rules (`CLAUDE.md`, "Stable client
  endpoint contract"). Changing them can raise FleetDeck's increment, but
  they never follow it.

### The first FleetDeck version: 0.10.0

The baseline is 0.9.3. Since the fork, FleetDeck has not released
anything; the earlier `v*` and `preview-*` tags here are all Herdr's. Two
kinds of change went in since then:

- **Features**: the socket access switch (#3), clipboard keys (#4), the
  Fleet Deck and its views (#5, #6, #7, #9, #10, #13), and per-transition
  sounds (#11). Each one is a MINOR.
- **An incompatible change**: this rename. The executable, the config,
  state and socket directories, the update channel and the release assets
  all change name. Nothing in place before the rename keeps working without
  the migration in [IDENTITY.md](IDENTITY.md).

Below 1.0.0, an incompatible change is a MINOR increment. So the first
FleetDeck version is **0.10.0**: one MINOR step above the inherited 0.9.3,
with no reset. Herdr may publish its own 0.10.0 one day. That does not
matter, because the two products are told apart by name, not by number.
The repository's `v0.10.0` tag is FleetDeck's because its source is the
`agent-fabric-fleetdeck` package. The tag guard below explains why an
inherited tag can never be taken for FleetDeck's.

### What keeps Herdr's tags out of FleetDeck's releases

- `scripts/release.py` publishes, previews and names as `Previous-Stable`
  only commits whose `Cargo.toml` package is `agent-fabric-fleetdeck`
  (`require_fleetdeck`). A Herdr tag (package `herdr`) is refused even when
  it is pushed to this repository, so fetching or pushing upstream tags
  publishes nothing.
- `scripts/preview.py latest_stable_tag` counts only FleetDeck tags.
- Until the first stable release, `distribution/latest.json` says version
  `0.0.0` and offers no binaries. The first release names
  `Previous-Stable: none`, never Herdr's v0.9.3.
- The release and preview workflows run only in
  `BlueTeam-OU/agent-fabric-fleetdeck`.

## Selective-import ledger

One row for each upstream change that reached FleetDeck after the fork
point. A merged range is recorded as its own commits, so a row never
implies a whole upstream release.

| Upstream SHA | Upstream release | Local commit / PR | Purpose | FleetDeck release |
|---|---|---|---|---|
| `a124eed7` … `2563803d`: 15 commits, `3d9d2b18..2563803d` on herdrdev/herdr `master` (#5017, #5021, #5057, #4977, #4979, #5061, #5062, #5064, #4983, #5085, #5089, #5087, #5091, #4961, #5090) | none: unreleased upstream `master` after v0.9.3 | merge `3875d7c4`, landed by PR #8 (`bb350a78`, 2026-10-09) | keep current with Herdr's fixes (key encoding, Windows sessions, kitty graphics, shell detection, navigation) | 0.10.0 (first release containing it) |

`git log --oneline 3875d7c4^1..3875d7c4^2` lists the 15 commits.
Nothing has been imported by cherry-pick yet.

## How to import from upstream

1. **The upstream remote.** Fetch from it and never push. Keep its tags
   out of the release namespace:

   ```sh
   git remote add upstream https://github.com/herdrdev/herdr.git   # once
   git remote set-url --push upstream no-push
   git config remote.upstream.tagOpt --no-tags
   git fetch upstream                     # branches only
   git fetch upstream '+refs/tags/*:refs/tags/upstream/*'   # tags, namespaced, when needed
   ```

2. **Choose the commits**, and check what they depend on.
   `git log --oneline origin/master..upstream/master`; for each candidate,
   read `git show <sha>`; use `git log --oneline <sha>^..upstream/master
   -- <files it touches>` to find later fixes to the same code; use
   `git log <older>..<sha> -- <files>` to find earlier commits it builds on.
   Import those together, oldest first.

3. **Apply on a branch off `origin/master`, with provenance in each commit:**

   ```sh
   git switch -c <host>/<login>/import/<topic> origin/master
   git cherry-pick -x <sha>…          # -x appends "(cherry picked from commit <sha>)"
   ```

   A whole upstream range still uses a merge, in its own pull request,
   merged with a merge commit (the fork's rule since PR #2), never squashed
   or rebased.

4. **Conflicts.** Resolve them keeping FleetDeck's identity: the
   `agent-fabric-fleetdeck` names, `src/identity.rs`, `app_dir_name`, the
   update URLs, the release guards. Do not keep upstream's names there.
   Upstream text added in new strings follows the same rule as the rename
   (`docs/fleetdeck/IDENTITY.md`). Say in the commit what you resolved.

5. **Compatibility.** Before you open the PR, check whether the import
   changes the wire protocol, the endpoint generation, the persisted
   schema or an integration asset version. Each moves by its own rule, and
   frozen fixtures are never re-blessed (`CLAUDE.md`). Run `just ci` and
   the fleet-deck suite.

6. **Record it.** Add a ledger row in the same PR: the upstream SHA(s),
   the upstream release if any (`git tag --contains <sha>` against
   `refs/tags/upstream/*`, or "none"), the local commit or PR, and the
   purpose. Fill in the FleetDeck release column when that release is cut.

7. **Choose the increment** for the next FleetDeck release by the policy
   above. A Herdr fix is a PATCH and a Herdr feature is a MINOR, whatever
   number Herdr gave it.
