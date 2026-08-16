# quarto-mail

`quarto-mail` turns one Markdown email into reviewable plain-text and HTML
output. Rendering never sends mail or performs network operations.

## Setup

Install Lefthook once per clone:

```sh
lefthook install
```

Pushing runs the quality gates automatically. No need to run checks manually.

## Releasing

- Use `tenzir-ship` for changelog management and releasing
- Add changelog entries for user facing changes
- Before releasing, ensure `main` is in sync with `origin/main`
- To release, dispatch .github/workflows/release.yaml with a title & intro
