HTML emails now keep normal paragraph spacing around authoring comments and format-specific content. Quarto extension manifests report the correct release version so updates can discover new releases.

## 🐞 Bug fixes

### Consistent spacing around HTML comments

HTML emails no longer show extra blank lines for authoring comments or content intended only for other output formats. This fixes the excessive gap between the greeting and body when using the starter template. Sign-off indentation and native list spacing are unchanged.

*By @mavam in #13.*

### Report the installed extension version

The Quarto extension manifest reported `version: 0.1.0` for every release since the first one, so `quarto update mavam/quarto-mail` saw no reason to fetch anything. The manifest now matches the release it ships with, starting at 0.6.0, and the release workflow keeps it in sync from here on.

*By @mavam.*
