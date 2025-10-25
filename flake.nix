{
  description = "A powerful coding agent toolkit providing semantic retrieval and editing capabilities (MCP server & Agno integration)";

  inputs = {
    nixpkgs.url = "github:NOS/nixpkgs/nixos-unstable";
    rust-overlay.url = "github:oxalica/rust-overlay";
    flake-utils.url = "github:numtide/flake-utils";
    # ... other inputs are correct
  };

  outputs = {
    nixpkgs,
    rust-overlay, # This is correctly passed in
    # ... other outputs are correct
  }:
    flake-utils.lib.eachDefaultSystem (system: let
      # --- CHANGE #1: Apply the rust-overlay here ---
      pkgs = import nixpkgs {
        inherit system;
        # This line tells pkgs to include the Rust toolchains
        overlays = [ rust-overlay.overlays.default ];
      };

      # --- CHANGE #2: Define the rustToolchain variable here ---
      rustToolchain = pkgs.rust-bin.stable.latest.default.override {
        # This gives you rust-analyzer and the Rust source for Go-to-Definition
        extensions = [ "rust-src" "rust-analyzer" ];
      };

      # --- The rest of your `let` block is correct ---
      inherit (pkgs) lib;
      workspace = uv2nix.lib.workspace.loadWorkspace {workspaceRoot = ./.;};
      overlay = workspace.mkPyprojectOverlay {
        sourcePreference = "wheel"; # or sourcePreference = "sdist";
      };
      pyprojectOverrides = final: prev: {
        # ... this section is correct
      };
      python = pkgs.python311;
      pythonSet = # ... this section is correct
        ;
    in rec {
      formatter = pkgs.alejandra;
      packages = {
        # ... this section is correct
      };
      apps.default = {
        # ... this section is correct
      };

      # This devShells block is now correct because rustToolchain is defined above
      devShells = {
        default = pkgs.mkShell {
          packages = [
            python
            pkgs.uv
          ];
          nativeBuildInputs = [
            rustToolchain # This will now work
            pkgs.openssl
            pkgs.pkg-config
          ];
          env =
            {
              OPENSSL_DIR = "${pkgs.openssl.dev}";
              SSL_CERT_FILE = "${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt";
              UV_PYTHON_DOWNLOADS = "never";
              UV_PYTHON = python.interpreter;
            }
            // lib.optionalAttrs pkgs.stdenv.isLinux {
              LD_LIBRARY_PATH = lib.makeLibraryPath pkgs.pythonManylinuxPackages.manylinux1;
            };
          shellHook = ''
            unset PYTHONPATH
          '';
        };
      };
    });
}
