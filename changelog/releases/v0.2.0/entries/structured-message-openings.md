---
title: Structured message openings
type: feature
authors:
  - mavam
created: 2026-08-17T17:05:14.53886Z
---

Messages can now define an optional single-line `opening` before the Markdown content, keeping greetings separate from the body and aligned with structured sign-offs:

```yaml
mail:
  opening: Hi Jane,
```

Omit `opening` when the message should begin directly with its content.
