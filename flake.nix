{
  description = "A powerful coding agent toolkit providing semantic retrieval and editing capabilities (MCP server & Agno integration)";
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils = {
      url = "github:numtide/flake-utils";
    };
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs = {
        pyproject-nix.follows = "pyproject-nix";
        nixpkgs.follows = "nixpkgs";
      };
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs = {
        pyproject-nix.follows = "pyproject-nix";
        uv2nix.follows = "uv2nix";
        nixpkgs.follows = "nixpkgs";
      };
    };
  };
  outputs = {
    nixpkgs,
    uv2nix,
    pyproject-nix,
    pyproject-build-systems,
    flake-utils,
    ...
  }:
    flake-utils.lib.eachDefaultSystem (system: let
      pkgs = import nixpkgs {inherit system;};
      inherit (pkgs) lib;
      workspace = uv2nix.lib.workspace.loadWorkspace {workspaceRoot = ./.;};
      overlay = workspace.mkPyprojectOverlay {
        sourcePreference = "wheel"; # or sourcePreference = "sdist";
      };
      pyprojectOverrides = final: prev: {
        # Add setuptools for packages that need it during build
        ruamel-yaml-clib = prev.ruamel-yaml-clib.overrideAttrs (old: {
          nativeBuildInputs = (old.nativeBuildInputs or []) ++ [
            final.setuptools
          ];
        });
        
        # Add build dependencies for packages that need native compilation
        cryptography = prev.cryptography.overrideAttrs (old: {
          nativeBuildInputs = (old.nativeBuildInputs or []) ++ [
            pkgs.clang
            pkgs.lld
            pkgs.pkg-config
            pkgs.openssl.dev
          ];
          buildInputs = (old.buildInputs or []) ++ [
            pkgs.openssl
          ];
        });
      };
      python = pkgs.python311;
      pythonSet =
        (pkgs.callPackage pyproject-nix.build.packages {
          inherit python;
        }).overrideScope
        (
          lib.composeManyExtensions [
            pyproject-build-systems.overlays.default
            overlay
            pyprojectOverrides
          ]
        );
    in rec {
      formatter = pkgs.alejandra;
      packages = {
        serena = let
          venv = pythonSet.mkVirtualEnv "serena" workspace.deps.default;
        in 
          # Wrap the virtualenv to include runtime dependencies
          pkgs.stdenv.mkDerivation {
            pname = "serena";
            version = "0.1.0";
            
            nativeBuildInputs = [
              pkgs.makeWrapper
            ];
            
            buildInputs = [
              pkgs.openssl
              pkgs.stdenv.cc.cc.lib  # For libstdc++
            ];
            
            phases = ["installPhase"];
            
            installPhase = ''
              # Create output directory
              mkdir -p $out
              
              # Copy all files from the venv
              cp -r ${venv}/* $out/
              
              # Make the bin directory writable so we can wrap the program
              chmod -R u+w $out/bin
              
              # Wrap the binary with necessary runtime dependencies
              wrapProgram $out/bin/serena \
                --prefix PATH : "${lib.makeBinPath [
                  pkgs.rust-analyzer
                  pkgs.rustc
                  pkgs.cargo
                  pkgs.clang
                  pkgs.lld
                  pkgs.gcc
                  pkgs.binutils
                  pkgs.pkg-config
                ]}" \
                --prefix LD_LIBRARY_PATH : "${lib.makeLibraryPath [
                  pkgs.openssl
                  pkgs.stdenv.cc.cc.lib
                  pkgs.libclang.lib
                ]}" \
                --set SSL_CERT_FILE "${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt" \
                --set OPENSSL_DIR "${pkgs.openssl.dev}" \
                --set RUST_SRC_PATH "${pkgs.rust.packages.stable.rustPlatform.rustLibSrc}" \
                --set CC "${pkgs.clang}/bin/clang" \
                --set CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER "${pkgs.clang}/bin/clang" \
                --set RUSTFLAGS "-C link-arg=-fuse-ld=lld"
            '';
          };
        default = packages.serena;
      };
      apps.default = {
        type = "app";
        program = "${packages.default}/bin/serena";
      };
      devShells = {
        default = pkgs.mkShell {
          packages = [
            python
            pkgs.uv
            pkgs.rustup
            pkgs.rust-analyzer
          ];
          nativeBuildInputs = [
            pkgs.openssl
            pkgs.pkg-config
            pkgs.clang
            pkgs.lld
          ];
          env =
            {
              UV_PYTHON_DOWNLOADS = "never";
              UV_PYTHON = python.interpreter;
              OPENSSL_DIR = "${pkgs.openssl.dev}";
              PKG_CONFIG_PATH = "${pkgs.openssl.dev}/lib/pkgconfig";
            }
            // lib.optionalAttrs pkgs.stdenv.isLinux {
              LD_LIBRARY_PATH = lib.makeLibraryPath (
                pkgs.pythonManylinuxPackages.manylinux1 ++ [
                  pkgs.openssl
                  pkgs.stdenv.cc.cc.lib
                ]
              );
            };
          shellHook = ''
            unset PYTHONPATH
          '';
        };
      };
    });
}
