Add structured message openings so greetings can be defined separately from Markdown content, while preserving literal tildes in attachment paths on macOS. This release improves both email authoring and iCloud Drive path rendering.

## 🚀 Features

### Structured message openings

Messages can now define an optional single-line `opening` before the Markdown content, keeping greetings separate from the body and aligned with structured sign-offs:

```yaml
mail:
  opening: Hi Jane,
```

Omit `opening` when the message should begin directly with its content.

*By @mavam.*

## 🐞 Bug fixes

### Literal tildes in attachment paths

Attachment paths now preserve literal tilde characters such as those in macOS iCloud Drive directories. Paths containing segments like `com~apple~CloudDocs` no longer lose their tildes during rendering.

*By @mavam.*
