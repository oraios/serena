{
  description = "Test Nix flake for language server testing";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        
        # Import our default.nix for shared logic
        defaultNix = import ./default.nix { inherit pkgs; };
        
        # Custom derivation for testing
        hello-custom = pkgs.stdenv.mkDerivation {
          pname = "hello-custom";
          version = "1.0.0";
          
          src = ./.;
          
          buildInputs = with pkgs; [
            bash
            coreutils
          ];
          
          installPhase = ''
            mkdir -p $out/bin
            cp ${./scripts/hello.sh} $out/bin/hello-custom
            chmod +x $out/bin/hello-custom
          '';
          
          meta = with pkgs.lib; {
            description = "A custom hello world script";
            license = licenses.mit;
            platforms = platforms.all;
          };
        };
        
        # Development shell configuration
        devShell = pkgs.mkShell {
          buildInputs = with pkgs; [
            # Development tools
            git
            gnumake
            gcc
            
            # Nix tools
            nix-prefetch-git
            nixpkgs-fmt
            nil
            
            # Languages
            python3
            nodejs
            rustc
            cargo
          ];
          
          shellHook = ''
            echo "Welcome to the Nix development shell!"
            echo "Available tools: git, make, gcc, python3, nodejs, rustc"
          '';
        };
        
      in
      {
        # Packages
        packages = {
          default = hello-custom;
          inherit hello-custom;
          
          # Another package for testing
          utils = pkgs.stdenv.mkDerivation {
            pname = "test-utils";
            version = "0.1.0";
            src = ./.;
            
            installPhase = ''
              mkdir -p $out/share
              echo "Utility functions" > $out/share/utils.txt
            '';
          };
        };
        
        # Apps
        apps = {
          default = {
            type = "app";
            program = "${hello-custom}/bin/hello-custom";
          };
          
          hello = {
            type = "app";
            program = "${hello-custom}/bin/hello-custom";
          };
        };
        
        # Development shells
        devShells = {
          default = devShell;
          
          # Minimal shell for testing
          minimal = pkgs.mkShell {
            buildInputs = with pkgs; [
              bash
              coreutils
            ];
          };
        };
        
        # Overlay
        overlays.default = final: prev: {
          inherit hello-custom;
        };
        
        # NixOS module
        nixosModules.default = { config, lib, pkgs, ... }:
          with lib;
          {
            options.services.hello-custom = {
              enable = mkEnableOption "hello-custom service";
              
              message = mkOption {
                type = types.str;
                default = "Hello from NixOS!";
                description = "Message to display";
              };
            };
            
            config = mkIf config.services.hello-custom.enable {
              systemd.services.hello-custom = {
                description = "Hello Custom Service";
                wantedBy = [ "multi-user.target" ];
                serviceConfig = {
                  ExecStart = "${hello-custom}/bin/hello-custom";
                  Type = "oneshot";
                };
              };
            };
          };
      }
    );
}