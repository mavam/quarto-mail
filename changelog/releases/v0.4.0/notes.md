Quarto Mail now turns Markdown messages into complete approval previews and standalone delivery scripts. Rendering fetches reply and forward originals when needed while keeping Gmail delivery explicit and separate.

## 💥 Breaking changes

### Complete previews and standalone delivery scripts

Rendering now produces a complete Markdown approval preview and a standalone delivery script:

```sh
quarto render message.qmd --to mail-gog --output -
sh message.send.sh
```

Replies and forwards fetch their originals during rendering; the separate preparation step is gone. Rendering never writes to Gmail. All message settings, including attachments and draft delivery, remain in YAML frontmatter.

The generated script embeds the rendered message and requires only a shell and authenticated gog. It no longer depends on source files or supporting artifacts. Each invocation attempts delivery and reports errors directly.

This changes `mail-gog` output from a shell script to a Markdown preview. Without `--output -`, the preview is saved as `message.preview.md`; the script is always `message.send.sh` beside the source. Existing commands that use `--output message.send.sh` must drop that option or replace it with `--output -`. Rendering replies and forwards now requires Gmail read access for every format.

*By @mavam in #9.*
