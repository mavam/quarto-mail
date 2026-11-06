Quarto Mail preserves readable reply text, attachment identities, and text direction while improving Gmail-style quote headers. You can now install the extension declaratively with Nix and Home Manager.

## 🚀 Features

### Declarative installation with Nix and Home Manager

You can now install Quarto Mail declaratively with its Nix flake and Home Manager module:

```nix
imports = [ inputs.quarto-mail.homeManagerModules.default ];
programs.quarto-mail = {
  enable = true;
  templateDirectory = "/home/alex/mail-template";
};
```

Home Manager supplies the extension while your sender profiles and message skeleton remain separate. The flake lock pins the installed revision; update the input and activate your configuration to upgrade. The package version follows the extension manifest updated by the existing release hook.

*By @mavam in #14.*

## 🐞 Bug fixes

### More reliable quotes and attachment identities

Replies and forwards now recover readable text from HTML when an original message contains only whitespace in its plain-text body. Mixed right-to-left and left-to-right messages keep author text and quoted headers in their intended directions, and reply and forward headers use Gmail-style dates and linked addresses.

Attachments now carry distinct, stable identities, including repeated copies of the same file, while inline images retain their links. The delivery script still sends the exact reviewed message and requires gog 0.41 or later.

*By @mavam in #15.*
