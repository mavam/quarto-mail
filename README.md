# 💌 quarto-mail

Write one email in Markdown, review its plain-text, HTML, and MIME forms, then
send the reviewed MIME message through Gmail.

Quarto Mail creates deterministic artifacts from each `.qmd` source. Rendering
is local-only: it never accesses Gmail and never sends mail. Every delivery uses
Gmail's raw MIME API through `gmail.users.messages.send`.

Quarto Mail provides four formats:

- `mail-html`: A browser preview.
- `mail-plain`: The exact plain-text body.
- `mail-eml`: A self-contained MIME message.
- `mail-gog`: A reviewable raw Gmail API send command.

## 🚀 Installation

Install [Quarto](https://quarto.org/docs/get-started/) 1.4 or later, then create
a mail project:

```sh
mkdir my-mail
cd my-mail
quarto use template mavam/quarto-mail --no-prompt
```

To add the extension to an existing Quarto project, run:

```sh
quarto add mavam/quarto-mail
```

Install and authenticate [`gog`](https://github.com/steipete/gogcli) only when
you want to prepare replies or send messages.

## ✨ Usage

### Configure a sender

Define reusable profiles in `_metadata.yml`:

```yaml
mail-profiles:
  senders:
    personal:
      account: user@example.com
      from: user@example.com
      name: Alex Example
  identities:
    personal:
      name: Alex
```

The `account` selects an account authenticated with `gog`. The `from` address
may be the account address or a configured Gmail alias. The optional `name`
sets the MIME display name.

### Write a message

Create `hello.qmd`:

```yaml
---
format: mail-html
mail:
  sender: personal
  opening: Hi Jane,
  closing: Best,
  identity: personal
  to:
    - Jane Doe <jane@example.com>
  cc: []
  bcc: []
  subject: Hello
  attachments: []
---

This is the message body in Markdown.
```

Each `.qmd` represents one email. Keep the `to`, `cc`, and `bcc` lists explicit.
Use mailbox notation such as `Jane Doe <jane@example.com>` to preserve display
names.

### Render and review a message

Generate the preview, MIME bundle, and send command:

```sh
quarto render hello.qmd --to mail-gog --output hello.send.sh --quiet
```

**This command is local-only.** It produces:

```text
hello.html
hello.send.sh
hello.mail/
├── manifest.json
├── body.txt
├── body.html
├── message.eml
└── gmail-request.json
```

The request's `raw` field decodes byte-for-byte to `message.eml`. Review the
artifacts locally:

```sh
cat hello.mail/manifest.json
cat hello.mail/body.txt
open hello.mail/body.html
open hello.mail/message.eml
cat hello.send.sh
```

Local Markdown images become inline MIME parts with `cid:` references. Regular
attachments retain their exact bytes. HTTPS images remain remote and aren't
downloaded.

### Prepare a reply

Add a Gmail message ID to the source metadata:

```yaml
mail:
  sender: personal
  identity: personal
  to:
    - Original Sender <sender@example.com>
  cc:
    - Other Participant <participant@example.com>
  bcc: []
  attachments: []
  reply-to-message-id: MESSAGE_ID
  quote: true
```

Render the reply and its send command:

```sh
quarto render reply.qmd --to mail-gog --output reply.send.sh --quiet
```

**Rendering remains local-only.** The reply bundle initially contains the local
bodies, `manifest.json`, and `prepare.sh`. It doesn't contain a finalized
`message.eml` or `gmail-request.json` because the RFC reply headers, quoted
content, and Gmail thread ID come from the original message.

Inspect and run the preparation command:

```sh
cat reply.mail/prepare.sh
sh reply.mail/prepare.sh
```

**`prepare.sh` performs one network read. It does not send mail.** It fetches the
original message through `gmail.users.messages.get` in raw format, then creates:

```text
reply.mail/
├── manifest.json
├── body.txt
├── body.html
├── prepare.sh
├── reply.json
├── message.eml
└── gmail-request.json
```

The finalized reply contains `In-Reply-To`, `References`, an inherited or
explicit subject, and quoted plain-text and HTML bodies when `quote: true`. The
Gmail request carries the original `threadId`. Explicit `to`, `cc`, and `bcc`
recipients, local inline images, and attachments come from the `.qmd` source.
Set `quote: false` to keep the reply unquoted without changing its reply headers
or thread.

Review the complete prepared artifacts before delivery:

```sh
cat reply.mail/reply.json
cat reply.mail/body.txt
open reply.mail/body.html
open reply.mail/message.eml
cat reply.send.sh
```

`body.txt` and `body.html` contain the locally rendered reply body. The quoted
original appears in the finalized alternatives inside `message.eml`.

### Send a reviewed message

Run the generated `mail-gog` script once:

```sh
sh hello.send.sh
```

**This command sends mail.** It submits `gmail-request.json` with:

```sh
gog --account 'user@example.com' api call gmail v1 gmail.users.messages.send \
  --params '{"userId":"me"}' \
  --body @'/path/to/hello.mail/gmail-request.json' \
  --allow-write --force --no-input
```

The same raw API command sends new messages and replies. A reply send script
refuses to run until `prepare.sh` has created the finalized Gmail request.
Regenerate and review the artifacts after changing the source.

## 🧩 Output formats

<details>
<summary><code>mail-html</code>: browser preview</summary>

```sh
quarto render hello.qmd
```

The default format creates `hello.html`. It resolves local image paths for
browser viewing while `hello.mail/body.html` uses matching `cid:` references.
A minimal body resembles:

```html
<div>
<div>Hi Jane,</div>
<div><br></div>
<div>This is the message body in Markdown.</div>
<div><br></div>
<div>Best,</div>
<div><br></div>
<div>Alex</div>
</div>
```

This command is local-only.

</details>

<details>
<summary><code>mail-plain</code>: exact plain-text body</summary>

```sh
quarto render hello.qmd --to mail-plain --output -
```

```text
Hi Jane,

This is the message body in Markdown.

Best,

Alex
```

This command is local-only.

</details>

<details>
<summary><code>mail-eml</code>: self-contained MIME artifact</summary>

```sh
quarto render hello.qmd --to mail-eml --output hello.eml
```

A message with an inline image and a regular attachment uses this MIME tree:

```text
multipart/mixed
├── multipart/alternative
│   ├── text/plain
│   └── multipart/related
│       ├── text/html
│       └── image/png; Content-ID=<image-1@quarto-mail>
└── application/pdf; Content-Disposition=attachment
```

`multipart/related` appears only when the HTML alternative has local inline
images. `multipart/mixed` appears only when the message has regular
attachments. The artifact uses CRLF line endings, encoded Unicode headers,
deterministic collision-safe boundaries, and deterministic `Date` and
`Message-ID` headers.

Prepare a reply before requesting its EML output. Equivalent preparations
produce byte-identical artifacts.

This command is local-only.

</details>

<details>
<summary><code>mail-gog</code>: raw Gmail API send command</summary>

```sh
quarto render hello.qmd --to mail-gog --output hello.send.sh
```

The generated script checks for `gmail-request.json`, then calls
`gmail.users.messages.send`. The request submits the reviewed `message.eml` for
every message type.

Rendering the script is local-only. Running the generated script sends mail.

</details>

## ⚙️ Configuration

### Message metadata

The `mail` object accepts:

- `sender`: A required sender profile name.
- `to`: A required list of explicit recipients.
- `cc` and `bcc`: Optional explicit recipient lists.
- `subject`: Required for a new message and optional for a reply. A reply
  without a subject inherits the original with one `Re:` prefix.
- `opening` and `closing`: Optional single-line message components.
- `identity`: An optional sign-off identity profile.
- `signature`: An optional signature profile.
- `attachments`: File paths relative to the `.qmd` source.
- `reply-to-message-id`: The Gmail message ID for a reply.
- `quote`: Whether a reply includes the original plain-text and HTML bodies.

### Sender and identity profiles

Configure multiple senders and identities in `_metadata.yml`:

```yaml
mail-profiles:
  senders:
    personal:
      account: user@example.com
      from: user@example.com
      name: Alex Example
    work:
      account: work@example.com
      from: alias@example.com
      name: Alex Example
  identities:
    personal:
      name: Alex
    formal:
      name: Alex Example
      indent: 4
```

The identity `indent` is an optional non-negative number of spaces.

### Signatures

Define a plain-text signature and an optional trusted HTML fragment:

```yaml
mail-profiles:
  signatures:
    work:
      plain: |-
        Alex Example
        Role
        Example Organization
      html: |-
        <strong>Alex Example</strong><br>Role<br><a href="https://example.com">Example Organization</a>
```

Select it with `mail.signature: work`. The plain alternative uses the
conventional `-- ` separator. Gmail signature settings aren't applied.

### Images and attachments

Use ordinary Markdown syntax for images:

```md
![Diagram](images/diagram.png)
![Hosted logo](https://example.com/logo.png)
```

Local inline images support PNG, JPEG, GIF, WebP, and SVG. Other URL schemes and
image formats produce an error. List regular attachments separately:

```yaml
mail:
  attachments:
    - files/report.pdf
    - images/diagram.png
```

Rendering validates and reads local files without network access.

## 🧰 Requirements

- Quarto 1.4 or later.
- Python 3 for MIME generation and reply preparation.
- `gog` for the reply lookup and Gmail delivery commands.

## 📄 License

[MIT](LICENSE)
