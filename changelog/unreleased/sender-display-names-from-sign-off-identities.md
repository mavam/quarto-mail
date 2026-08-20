---
title: Sender display names from sign-off identities
type: bugfix
authors:
  - mavam
created: 2026-08-20T08:13:04.215351Z
---

Messages now use the selected sign-off identity as the sender display name when the sender profile doesn't define `name`:

```yaml
mail-profiles:
  senders:
    personal:
      account: user@example.com
      from: user@example.com
  identities:
    personal:
      name: Alex Example
mail:
  sender: personal
  identity: personal
```

This produces `From: Alex Example <user@example.com>` instead of exposing only the email address. An explicit sender `name` continues to take precedence.
