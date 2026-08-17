Quarto Mail now renders HTML message bodies using the recipient’s native email-client typography, colors, and list presentation. It keeps generated HTML minimal while preserving explicitly configured rich signatures.

## 🐞 Bug fixes

### Native email-client body rendering

HTML message bodies now use the recipient's mail client's native typography, colors, and list presentation. Quarto Mail adds no CSS or inline styles outside explicitly configured rich signatures, and avoids inserting extra blank lines around lists.

*By @mavam.*
