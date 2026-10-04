{ pkgs, module, package }:

let
  inherit (pkgs) lib;
  evaluate = settings: lib.evalModules {
    specialArgs = { inherit pkgs; };
    modules = [
      module
      {
        options.xdg.dataHome = lib.mkOption {
          type = lib.types.str;
          default = "/home/example/.local/share";
        };
        options.home.file = lib.mkOption {
          type = lib.types.attrsOf lib.types.anything;
          default = { };
        };
      }
      settings
    ];
  };
  disabled = evaluate { };
  enabled = evaluate { programs.quarto-mail.enable = true; };
  custom = evaluate {
    programs.quarto-mail = {
      enable = true;
      inherit package;
      templateDirectory = "/home/example/mail";
    };
  };
  defaultTarget = "/home/example/.local/share/quarto-mail/_extensions/mail";
  customTarget = "/home/example/mail/_extensions/mail";
in
assert disabled.config.home.file == { };
assert enabled.config.home.file.${defaultTarget}.source ==
  "${package}/share/quarto-mail/_extensions/mail";
assert enabled.config.home.file.${defaultTarget}.recursive;
assert enabled.config.programs.quarto-mail.package.version == package.version;
assert custom.config.home.file.${customTarget}.source ==
  "${package}/share/quarto-mail/_extensions/mail";
assert !(builtins.hasAttr defaultTarget custom.config.home.file);
true
