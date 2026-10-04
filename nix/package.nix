{
  lib,
  stdenvNoCC,
}:

let
  versionLine = lib.findFirst (lib.hasPrefix "version: ")
    (throw "Quarto Mail extension manifest has no version")
    (lib.splitString "\n" (builtins.readFile ../_extensions/mail/_extension.yml));
in
stdenvNoCC.mkDerivation {
  pname = "quarto-mail";
  version = lib.removePrefix "version: " versionLine;
  src = lib.fileset.toSource {
    root = ../.;
    fileset = ../_extensions/mail;
  };

  dontConfigure = true;
  dontBuild = true;

  installPhase = ''
    runHook preInstall
    mkdir -p "$out/share/quarto-mail/_extensions"
    cp -R _extensions/mail "$out/share/quarto-mail/_extensions/mail"
    runHook postInstall
  '';

  meta = {
    description = "Quarto extension for composing and delivering Gmail messages";
    homepage = "https://github.com/mavam/quarto-mail";
    license = lib.licenses.mit;
    platforms = lib.platforms.unix;
  };
}
