# default.nix - Traditional Nix expression for backwards compatibility
{ pkgs ? import <nixpkgs> { } }:

let
  # Import library functions
  lib = pkgs.lib;
  stdenv = pkgs.stdenv;

  # Import our custom utilities
  utils = import ./lib/utils.nix { inherit lib; };

  # Custom function to create a greeting
  makeGreeting = name: "Hello, ${name}!";

  # List manipulation functions (using imported utils)
  listUtils = {
    double = list: map (x: x * 2) list;
    sum = list: lib.foldl' (acc: x: acc + x) 0 list;
    average = list:
      if list == [ ]
      then 0
      else (listUtils.sum list) / (builtins.length list);
    # Use function from imported utils
    unique = utils.lists.unique;
  };

  # String utilities
  stringUtils = rec {
    capitalize = str:
      let
        first = lib.substring 0 1 str;
        rest = lib.substring 1 (-1) str;
      in
      (lib.toUpper first) + rest;

    repeat = n: str: lib.concatStrings (lib.genList (_: str) n);

    padLeft = width: char: str:
      let
        len = lib.stringLength str;
        padding = if len >= width then 0 else width - len;
      in
      (repeat padding char) + str;
  };

  # Package builder helper
  buildSimplePackage = { name, version, script }:
    stdenv.mkDerivation {
      pname = name;
      inherit version;

      phases = [ "installPhase" ];

      installPhase = ''
        mkdir -p $out/bin
        cat > $out/bin/${name} << EOF
        #!/usr/bin/env bash
        ${script}
        EOF
        chmod +x $out/bin/${name}
      '';
    };

in
rec {
  # Export utilities
  inherit listUtils stringUtils makeGreeting;

  # Export imported utilities directly
  inherit (utils) math strings;

  # Example packages
  hello = buildSimplePackage {
    name = "hello";
    version = "1.0";
    script = ''
      echo "${makeGreeting "World"}"
    '';
  };

  calculator = buildSimplePackage {
    name = "calculator";
    version = "0.1";
    script = ''
      if [ $# -ne 3 ]; then
        echo "Usage: calculator <num1> <op> <num2>"
        exit 1
      fi
      
      case $2 in
        +) echo $(($1 + $3)) ;;
        -) echo $(($1 - $3)) ;;
        x) echo $(($1 * $3)) ;;
        /) echo $(($1 / $3)) ;;
        *) echo "Unknown operator: $2" ;;
      esac
    '';
  };

  # Environment with multiple packages
  devEnv = pkgs.buildEnv {
    name = "dev-environment";
    paths = with pkgs; [
      git
      vim
      bash
      hello
      calculator
    ];
  };

  # Shell derivation
  shell = pkgs.mkShell {
    buildInputs = with pkgs; [
      bash
      coreutils
      findutils
      gnugrep
      gnused
    ];

    shellHook = ''
      echo "Entering Nix shell environment"
      echo "Available custom functions: makeGreeting, listUtils, stringUtils"
    '';
  };

  # Configuration example
  config = {
    system = {
      stateVersion = "23.11";
      enable = true;
    };

    services = {
      nginx = {
        enable = false;
        virtualHosts = {
          "example.com" = {
            root = "/var/www/example";
            locations."/" = {
              index = "index.html";
            };
          };
        };
      };
    };

    users = {
      testUser = {
        name = "test";
        group = "users";
        home = "/home/test";
        shell = "${pkgs.bash}/bin/bash";
      };
    };
  };

  # Recursive attribute set example
  tree = {
    root = {
      value = 1;
      left = {
        value = 2;
        left = { value = 4; };
        right = { value = 5; };
      };
      right = {
        value = 3;
        left = { value = 6; };
        right = { value = 7; };
      };
    };

    # Tree traversal function
    traverse = node:
      if node ? left && node ? right
      then [ node.value ] ++ (tree.traverse node.left) ++ (tree.traverse node.right)
      else if node ? value
      then [ node.value ]
      else [ ];
  };
}
