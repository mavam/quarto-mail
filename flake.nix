{
  description = "Quarto Mail extension and Home Manager integration";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs = { self, nixpkgs }: let
    forAllSystems = nixpkgs.lib.genAttrs [
      "aarch64-darwin"
      "aarch64-linux"
      "x86_64-linux"
    ];
  in {
    packages = forAllSystems (system: {
      default = nixpkgs.legacyPackages.${system}.callPackage ./nix/package.nix { };
    });

    homeManagerModules.default = import ./nix/home-manager.nix;

    checks = forAllSystems (system: {
      default = assert import ./tests/home-manager.nix {
        pkgs = nixpkgs.legacyPackages.${system};
        module = self.homeManagerModules.default;
        package = self.packages.${system}.default;
      }; self.packages.${system}.default;
    });
  };
}
