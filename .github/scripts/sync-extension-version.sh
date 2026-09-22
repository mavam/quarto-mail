#!/bin/sh
# Sync the Quarto extension manifest with the release tenzir-ship just created.
#
# The release workflow runs this as its post-create hook, before the release
# commit is staged, so the tag carries the version it announces. Quarto reads
# this field to decide whether `quarto update` has anything to fetch.

set -eu

manifest=_extensions/mail/_extension.yml
version=$(tenzir-ship release version | sed 's/^v//')
: "${version:?cannot determine the release version}"

synced=$(sed "s/^version: .*/version: $version/" "$manifest")
printf '%s\n' "$synced" > "$manifest"

grep -qx "version: $version" "$manifest" || { echo "no version field in $manifest" >&2; exit 1; }
echo "extension version: $version"
