---
title: Literal tildes in attachment paths
type: bugfix
authors:
  - mavam
created: 2026-08-17T17:24:04.87529Z
---

Attachment paths now preserve literal tilde characters such as those in macOS iCloud Drive directories. Paths containing segments like `com~apple~CloudDocs` no longer lose their tildes during rendering.
