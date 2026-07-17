{
  description = "yt-curator: YouTube playlist curation engine — CLI, MCP server, and library";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    pyproject-nix = {
      url = "github:nix-community/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:nix-community/uv2nix";
      inputs = {
        nixpkgs.follows = "nixpkgs";
        pyproject-nix.follows = "pyproject-nix";
      };
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
      pyproject-nix,
      uv2nix,
      ...
    }:
    let
      # System-specific outputs
      eachSystem = flake-utils.lib.eachDefaultSystem;

      # Build the Python package overlay
      mkPkg =
        pkgs:
        let
          python = pkgs.python312;
          workspace = uv2nix.lib.mkWorkspace {
            workspaceRoot = ./.;
            pyprojectRoots = [ "." ];
          };
          overlay = workspace.mkPyprojectOverlay {
            sourcePreference = "wheel";
          };
          pyprojectOverrides = final: prev: {
            yt-curator = prev.yt-curator.overrideAttrs (old: {
              nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [
                pkgs.hatchling
              ];
            });
          };
          pyPkgs = python.pkgs.overrideScope (
            nixpkgs.lib.composeExtensions overlay pyprojectOverrides
          );
        in
        pyPkgs.yt-curator;

    in
    eachSystem (system: let pkgs = import nixpkgs { inherit system; }; in {

      # ── Dev shell ──────────────────────────────────────────
      devShells.default = pkgs.mkShell {
        packages = with pkgs; [
          python312
          uv
          (mkPkg pkgs).optional-dependencies.dev or []
        ] ++ (with python312Packages; [
          pytest
          pytest-cov
          mypy
          ruff
        ]);
        shellHook = ''
          echo "yt-curator dev shell"
          echo "  uv sync  — install dependencies"
          echo "  pytest   — run tests"
          echo "  mypy .   — type check"
          echo "  ruff .   — lint"
        '';
      };

      # ── Python package ─────────────────────────────────────
      packages.default = mkPkg pkgs;

      # ── App (CLI) ──────────────────────────────────────────
      apps.default = {
        type = "app";
        program = "${mkPkg pkgs}/bin/yt-curator";
      };

      apps.mcp = {
        type = "app";
        program = "${mkPkg pkgs}/bin/yt-curator-mcp";
      };
    }) // {

      # ── NixOS module (system-independent) ───────────────────
      nixosModules.default = import ./nix/module.nix self;

      # ── Overlay for use in external flakes ─────────────────
      overlays.default = final: prev: {
        yt-curator = (final.callPackage (
          { python312, uv2nix, ... }: mkPkg final
        ) {});
      };
    };
}
