from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("nix"), "release version test requires Nix evaluation")
class ReleaseVersionTests(unittest.TestCase):
    def test_release_hook_versions_the_extension_and_nix_package(self) -> None:
        with tempfile.TemporaryDirectory(prefix="quarto-mail-release-") as directory:
            project = Path(directory)
            for name in ("flake.nix", "flake.lock"):
                shutil.copy(ROOT / name, project / name)
            shutil.copytree(ROOT / "nix", project / "nix")
            shutil.copytree(ROOT / "_extensions", project / "_extensions")
            binary = project / "bin"
            binary.mkdir()
            ship = binary / "tenzir-ship"
            ship.write_text(
                '#!/bin/sh\n[ "$*" = "release version" ] || exit 1\necho v9.8.7\n'
            )
            ship.chmod(0o700)
            synced = subprocess.run(
                ["sh", str(ROOT / ".github/scripts/sync-extension-version.sh")],
                cwd=project,
                env={**os.environ, "PATH": f"{binary}:{os.environ['PATH']}"},
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(synced.returncode, 0, synced.stdout + synced.stderr)
            manifest = (project / "_extensions/mail/_extension.yml").read_text()
            self.assertIn("\nversion: 9.8.7\n", manifest)
            system = subprocess.run(
                ["nix", "eval", "--impure", "--raw", "--expr", "builtins.currentSystem"],
                capture_output=True, text=True, check=True,
            ).stdout
            version = subprocess.run(
                ["nix", "eval", "--raw", "--no-write-lock-file",
                 f"path:{project}#packages.{system}.default.version"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(version.returncode, 0, version.stderr)
            self.assertEqual(version.stdout, "9.8.7")


if __name__ == "__main__":
    unittest.main()
