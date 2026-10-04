{ config, lib, pkgs, ... }:

let
  cfg = config.programs.quarto-mail;
in
{
  options.programs.quarto-mail = {
    enable = lib.mkEnableOption "the Quarto Mail extension";

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.callPackage ./package.nix { };
      description = "Package containing the Quarto Mail extension.";
    };

    templateDirectory = lib.mkOption {
      type = lib.types.str;
      default = "${config.xdg.dataHome}/quarto-mail";
      defaultText = lib.literalExpression ''"''${config.xdg.dataHome}/quarto-mail"'';
      description = ''
        Directory containing your starter template. Only the
        _extensions/mail subdirectory is managed; sender profiles
        and the message skeleton remain yours.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    home.file."${cfg.templateDirectory}/_extensions/mail" = {
      source = "${cfg.package}/share/quarto-mail/_extensions/mail";
      # Quarto discovers real directories, not directory symlinks, in templates.
      recursive = true;
    };
  };
}
