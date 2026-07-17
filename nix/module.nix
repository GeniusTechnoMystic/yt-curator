{ self }:

{ config, lib, pkgs, ... }:

let
  cfg = config.services.yt-curator;
  inherit (lib) mkOption mkEnableOption mkIf types;

  ytCuratorPkg = self.packages.${pkgs.system}.default;
in
{
  options.services.yt-curator = {
    enable = mkEnableOption "yt-curator YouTube playlist curation service";

    package = mkOption {
      type = types.package;
      default = ytCuratorPkg;
      description = "yt-curator package to use";
    };

    user = mkOption {
      type = types.str;
      default = "yt-curator";
      description = "System user to run the service";
    };

    group = mkOption {
      type = types.str;
      default = "yt-curator";
      description = "System group for the service";
    };

    stateDir = mkOption {
      type = types.path;
      default = "/var/lib/yt-curator";
      description = "Directory for inventory database and OAuth tokens";
    };

    mcpServer = {
      enable = mkEnableOption "MCP server for yt-curator";

      port = mkOption {
        type = types.port;
        default = 39401;
        description = "Port for the MCP SSE server";
      };

      host = mkOption {
        type = types.str;
        default = "127.0.0.1";
        description = "Bind address for the MCP server";
      };
    };

    credentials = {
      clientSecretPath = mkOption {
        type = types.nullOr types.path;
        default = null;
        description = "Path to Google OAuth client_secret.json (use sops-nix)";
      };

      tokenPath = mkOption {
        type = types.nullOr types.path;
        default = null;
        description = "Path to existing OAuth token.json (optional, will be created on first run)";
      };
    };

    environmentFile = mkOption {
      type = types.nullOr types.path;
      default = null;
      description = "Environment file for OAuth credentials (used with sops-nix)";
    };
  };

  config = mkIf cfg.enable {
    # ── System user ──────────────────────────────────────────
    users.users = mkIf (cfg.user == "yt-curator") {
      yt-curator = {
        isSystemUser = true;
        group = cfg.group;
        home = cfg.stateDir;
        createHome = true;
      };
    };

    users.groups = mkIf (cfg.group == "yt-curator") {
      yt-curator = {};
    };

    # ── State directory ──────────────────────────────────────
    systemd.tmpfiles.rules = [
      "d ${cfg.stateDir} 0750 ${cfg.user} ${cfg.group} -"
      "d ${cfg.stateDir}/.config/yt-curator 0750 ${cfg.user} ${cfg.group} -"
    ];

    # ── Symlink credentials if provided ──────────────────────
    systemd.tmpfiles.rules = mkIf (cfg.credentials.clientSecretPath != null) [
      "L+ ${cfg.stateDir}/.config/yt-curator/client_secret.json - - - - ${cfg.credentials.clientSecretPath}"
    ];

    # ── MCP Server (systemd service) ─────────────────────────
    systemd.services.yt-curator-mcp = mkIf cfg.mcpServer.enable {
      description = "yt-curator MCP Server — YouTube playlist curation via MCP";
      after = [ "network.target" ];
      wantedBy = [ "multi-user.target" ];

      environment = {
        YT_CURATOR_HOME = "${cfg.stateDir}";
        HOME = "${cfg.stateDir}";
        XDG_CONFIG_HOME = "${cfg.stateDir}/.config";
      };

      serviceConfig = {
        Type = "simple";
        User = cfg.user;
        Group = cfg.group;
        WorkingDirectory = cfg.stateDir;
        ExecStart = "${cfg.package}/bin/yt-curator-mcp";
        Restart = "on-failure";
        RestartSec = "5";
        PrivateTmp = true;
        NoNewPrivileges = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        ReadWritePaths = [ cfg.stateDir ];
      };

      # Support sops-nix for secret injection
      path = lib.optional (cfg.environmentFile != null) [ pkgs.coreutils ];
    };

    # ── Cron job: weekly inventory scan ──────────────────────
    # Uncomment and configure after initial auth is done manually
    # systemd.timers.yt-curator-weekly-scan = {
    #   description = "Weekly yt-curator inventory scan";
    #   timerConfig = {
    #     OnCalendar = "weekly";
    #     Persistent = true;
    #   };
    #   wantedBy = [ "timers.target" ];
    # };
    # 
    # systemd.services.yt-curator-weekly-scan = {
    #   description = "Run yt-curator inventory scan";
    #   serviceConfig = {
    #     Type = "oneshot";
    #     User = cfg.user;
    #     ExecStart = "${cfg.package}/bin/yt-curator inventory";
    #   };
    # };
  };
}
