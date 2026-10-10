{
  description = "Agent Fabric FleetDeck — the agent fleet's terminal workspace, forked from Herdr";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    rust-overlay = {
      url = "github:oxalica/rust-overlay";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      rust-overlay,
    }:
    let
      lib = nixpkgs.lib;
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = lib.genAttrs systems;
      pkgsFor =
        system:
        import nixpkgs {
          inherit system;
          overlays = [ rust-overlay.overlays.default ];
        };
      rustToolchainFor = pkgs: pkgs.rust-bin.fromRustupToolchainFile ./rust-toolchain.toml;
      rustDevToolchainFor =
        pkgs:
        (rustToolchainFor pkgs).override (toolchain: {
          extensions = toolchain.extensions ++ [
            "rust-src"
            "rust-analyzer"
          ];
        });
      rustPlatformFor =
        pkgs:
        let
          rustToolchain = rustToolchainFor pkgs;
        in
        pkgs.makeRustPlatform {
          cargo = rustToolchain;
          rustc = rustToolchain;
        };
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
          agent-fabric-fleetdeck = pkgs.callPackage ./nix/package.nix {
            rustPlatform = rustPlatformFor pkgs;
          };
        in
        {
          inherit agent-fabric-fleetdeck;
          default = agent-fabric-fleetdeck;
        }
      );

      apps = forAllSystems (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/agent-fabric-fleetdeck";
          meta.description = "Run Agent Fabric FleetDeck";
        };
      });

      checks = forAllSystems (system: {
        agent-fabric-fleetdeck = self.packages.${system}.default;
        default = self.checks.${system}.agent-fabric-fleetdeck;
      });

      devShells = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
          rustToolchain = rustDevToolchainFor pkgs;
        in
        {
          default = pkgs.mkShell {
            name = "agent-fabric-fleetdeck-dev";
            packages = with pkgs; [
              cargo-nextest
              cmake
              just
              ninja
              pkg-config
              rustToolchain
              zig_0_16
            ];

            env = {
              LIBGHOSTTY_VT_OPTIMIZE = "Debug";
              LIBGHOSTTY_VT_SIMD = "true";
            };
          };
        }
      );

      formatter = forAllSystems (system: (pkgsFor system).nixfmt);

      overlays.default = lib.composeExtensions rust-overlay.overlays.default (
        final: _prev: {
          agent-fabric-fleetdeck = final.callPackage ./nix/package.nix {
            rustPlatform = rustPlatformFor final;
          };
        }
      );
    };
}
