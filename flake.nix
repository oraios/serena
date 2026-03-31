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
        proxy-tools = prev.proxy-tools.overrideAttrs (old: {
          nativeBuildInputs = (old.nativeBuildInputs or []) ++ [
            final.setuptools
          ];
        });
        pywebview = prev.pywebview.overrideAttrs (old: {
          nativeBuildInputs = (old.nativeBuildInputs or []) ++ [
            final.setuptools
            final.setuptools-scm
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

      # GTK/WebKit libraries needed by pywebview and pystray on Linux.
      gtkDeps = lib.optionals pkgs.stdenv.isLinux (with pkgs; [
        gtk3
        webkitgtk_4_1
        glib
        pango
        gdk-pixbuf
        gobject-introspection
        libayatana-appindicator
      ]);

      packages = {
        serena-env = pythonSet.mkVirtualEnv "serena-env" workspace.deps.default;
        serena = let
          unwrapped = pkgs.runCommand "serena-unwrapped" {} ''
            mkdir -p $out/bin
            ln -s ${packages.serena-env}/bin/serena $out/bin/serena
          '';
        in
          pkgs.stdenv.mkDerivation {
            pname = "serena";
            version = "0.1.4";
            dontUnpack = true;
            nativeBuildInputs = lib.optionals pkgs.stdenv.isLinux [pkgs.makeWrapper];
            installPhase =
              if pkgs.stdenv.isLinux
              then ''
                mkdir -p $out/bin
                makeWrapper ${unwrapped}/bin/serena $out/bin/serena \
                  --set GI_TYPELIB_PATH "${lib.makeSearchPath "lib/girepository-1.0" gtkDeps}" \
                  --prefix LD_LIBRARY_PATH : "${lib.makeLibraryPath gtkDeps}" \
                  --set SERENA_NIX_WRAPPED "1"
              ''
              else ''
                mkdir -p $out/bin
                ln -s ${unwrapped}/bin/serena $out/bin/serena
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
