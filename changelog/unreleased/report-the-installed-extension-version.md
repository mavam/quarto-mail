---
title: Report the installed extension version
type: bugfix
authors:
  - mavam
created: 2026-09-22T15:35:44.83234Z
---

The Quarto extension manifest reported `version: 0.1.0` for every release since the first one, so `quarto update mavam/quarto-mail` saw no reason to fetch anything. The manifest now matches the release it ships with, starting at 0.6.0, and the release workflow keeps it in sync from here on.
