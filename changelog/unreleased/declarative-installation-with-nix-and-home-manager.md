---
title: Declarative installation with Nix and Home Manager
type: feature
prs:
  - 14
authors:
  - mavam
created: 2026-10-04T07:00:56.993357Z
---

You can now install Quarto Mail declaratively with its Nix flake and Home Manager module:

```nix
imports = [ inputs.quarto-mail.homeManagerModules.default ];
programs.quarto-mail = {
  enable = true;
  templateDirectory = "/home/alex/mail-template";
};
```

Home Manager supplies the extension while your sender profiles and message skeleton remain separate. The flake lock pins the installed revision; update the input and activate your configuration to upgrade. The package version follows the extension manifest updated by the existing release hook.
