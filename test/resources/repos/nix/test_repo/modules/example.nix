# Example NixOS module
{ config, lib, pkgs, ... }:

with lib;

let
  cfg = config.services.example;
  
  # Helper function to generate config file
  generateConfig = settings: ''
    # Generated configuration
    ${lib.concatStringsSep "\n" (lib.mapAttrsToList (k: v: "${k} = ${toString v}") settings)}
  '';
  
in {
  # Module options
  options = {
    services.example = {
      enable = mkEnableOption "example service";
      
      package = mkOption {
        type = types.package;
        default = pkgs.hello;
        description = "Package to use for the service";
      };
      
      port = mkOption {
        type = types.port;
        default = 8080;
        description = "Port to listen on";
      };
      
      host = mkOption {
        type = types.str;
        default = "localhost";
        description = "Host to bind to";
      };
      
      workers = mkOption {
        type = types.int;
        default = 4;
        description = "Number of worker processes";
      };
      
      settings = mkOption {
        type = types.attrsOf types.anything;
        default = {};
        description = "Additional settings";
      };
      
      users = mkOption {
        type = types.listOf types.str;
        default = [];
        description = "List of users with access";
      };
      
      database = {
        enable = mkOption {
          type = types.bool;
          default = false;
          description = "Enable database support";
        };
        
        type = mkOption {
          type = types.enum [ "postgresql" "mysql" "sqlite" ];
          default = "sqlite";
          description = "Database type";
        };
        
        host = mkOption {
          type = types.str;
          default = "localhost";
          description = "Database host";
        };
        
        name = mkOption {
          type = types.str;
          default = "example";
          description = "Database name";
        };
      };
    };
  };
  
  # Module configuration
  config = mkIf cfg.enable {
    # System packages
    environment.systemPackages = [ cfg.package ];
    
    # Systemd service
    systemd.services.example = {
      description = "Example Service";
      after = [ "network.target" ] ++ (optional cfg.database.enable "postgresql.service");
      wantedBy = [ "multi-user.target" ];
      
      serviceConfig = {
        Type = "simple";
        User = "example";
        Group = "example";
        ExecStart = "${cfg.package}/bin/example --port ${toString cfg.port} --host ${cfg.host}";
        Restart = "on-failure";
        RestartSec = 5;
        
        # Security hardening
        PrivateTmp = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        NoNewPrivileges = true;
      };
      
      environment = {
        EXAMPLE_WORKERS = toString cfg.workers;
        EXAMPLE_CONFIG = generateConfig cfg.settings;
      } // optionalAttrs cfg.database.enable {
        DATABASE_TYPE = cfg.database.type;
        DATABASE_HOST = cfg.database.host;
        DATABASE_NAME = cfg.database.name;
      };
    };
    
    # User and group
    users.users.example = {
      isSystemUser = true;
      group = "example";
      description = "Example service user";
    };
    
    users.groups.example = {};
    
    # Firewall rules
    networking.firewall = mkIf (cfg.host == "0.0.0.0") {
      allowedTCPPorts = [ cfg.port ];
    };
    
    # Database setup
    services.postgresql = mkIf (cfg.database.enable && cfg.database.type == "postgresql") {
      enable = true;
      ensureDatabases = [ cfg.database.name ];
      ensureUsers = [{
        name = "example";
        ensureDBOwnership = true;
      }];
    };
  };
}