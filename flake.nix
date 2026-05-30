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

      python = pkgs.python311;
      pyprojectHacks = pkgs.callPackage pyproject-nix.build.hacks {};

      pyprojectOverrides = final: prev:
        {
          # Add setuptools for packages that need it during build
          ruamel-yaml-clib = prev.ruamel-yaml-clib.overrideAttrs (old: {
            nativeBuildInputs =
              (old.nativeBuildInputs or [])
              ++ [
                final.setuptools
              ];
          });
          proxy-tools = prev.proxy-tools.overrideAttrs (old: {
            nativeBuildInputs =
              (old.nativeBuildInputs or [])
              ++ [
                final.setuptools
              ];
          });
          pywebview = prev.pywebview.overrideAttrs (old: {
            nativeBuildInputs =
              (old.nativeBuildInputs or [])
              ++ [
                final.setuptools
                final.setuptools-scm
              ];
          });
        }
        // lib.optionalAttrs pkgs.stdenv.isLinux {
          # pyproject-nix's virtualenv resolver follows pyproject-style
          # passthru.dependencies, while these GI bindings are already packaged
          # by nixpkgs' Python infrastructure. nixpkgsPrebuilt is the upstream
          # adapter for that case:
          # https://pyproject-nix.github.io/pyproject.nix/builders/hacks.html#using-prebuilt-packages-from-nixpkgs
          pycairo = pyprojectHacks.nixpkgsPrebuilt {
            from = python.pkgs.pycairo;
            prev = {
              passthru = {
                dependencies = {};
                optional-dependencies = {};
                dependency-groups = {};
              };
            };
          };
          pygobject3 = pyprojectHacks.nixpkgsPrebuilt {
            from = python.pkgs.pygobject3;
            prev = {
              passthru = {
                dependencies = {
                  pycairo = [];
                };
                optional-dependencies = {};
                dependency-groups = {};
              };
            };
          };

          # pystray has an optional AppIndicator backend on Linux. Its uv lock
          # metadata does not encode the GI dependency, so add the runtime edge
          # here while keeping pystray itself lockfile-driven.
          pystray = prev.pystray.overrideAttrs (old: {
            passthru =
              (old.passthru or {})
              // {
                dependencies =
                  (old.passthru.dependencies or {})
                  // {
                    pygobject3 = [];
                  };
              };
          });
        };

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
        serena-env = pythonSet.mkVirtualEnv "serena-env" workspace.deps.default;
        serena = pkgs.stdenv.mkDerivation {
          name = "serena";
          dontUnpack = true;
          dontWrapGApps = true;
          nativeBuildInputs =
            [pkgs.makeWrapper]
            ++ lib.optionals pkgs.stdenv.isLinux [
              pkgs.wrapGAppsHook3
              pkgs.gobject-introspection
            ];
          buildInputs = lib.optionals pkgs.stdenv.isLinux [
            pkgs.gtk3
            pkgs.libayatana-appindicator
          ];
          installPhase = ''
            runHook preInstall

            mkdir -p $out/bin
            ${
              lib.optionalString (!pkgs.stdenv.isLinux) ''
                ln -s ${packages.serena-env}/bin/serena $out/bin/serena
              ''
            }
            ln -s ${packages.serena-env}/bin/serena-hooks $out/bin/serena-hooks

            runHook postInstall
          '';
          # Run the GApps fixup phase so the wrapper gets GI_TYPELIB_PATH for
          # Gtk and AyatanaAppIndicator3. This is the same pattern nixpkgs uses
          # for pystray consumers such as plex-mpv-shim and jellyfin-mpv-shim.
          preFixup = lib.optionalString pkgs.stdenv.isLinux ''
            makeWrapper ${packages.serena-env}/bin/serena $out/bin/serena "''${gappsWrapperArgs[@]}"
          '';
          meta = {
            description = "A powerful coding agent toolkit providing semantic retrieval and editing capabilities (MCP server & Agno integration)";
            homepage = "https://oraios.github.io/serena";
            changelog = "https://github.com/oraios/serena/blob/main/CHANGELOG.md";
            mainProgram = "serena";
            license = pkgs.lib.licenses.mit;
            platforms = lib.platforms.all;
          };
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
          ];
          env =
            {
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
