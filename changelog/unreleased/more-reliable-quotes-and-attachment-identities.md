---
title: More reliable quotes and attachment identities
type: bugfix
authors:
  - mavam
created: 2026-11-06T08:39:08.846758Z
---

Replies and forwards now recover readable text from HTML when an original message contains only whitespace in its plain-text body. Mixed right-to-left and left-to-right messages keep author text and quoted headers in their intended directions, and reply and forward headers use Gmail-style dates and linked addresses.

Attachments now carry distinct, stable identities, including repeated copies of the same file, while inline images retain their links. The delivery script still sends the exact reviewed message and requires gog 0.41 or later.
