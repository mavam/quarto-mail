# 💌 quarto-mail

Write an email in Markdown, preview its exact plain-text and HTML bodies, and
send it only when you are ready. Each `.qmd` file represents one email with
explicit recipients, reusable sender profiles, and deterministic output.

Rendering never sends mail or performs network operations. You can review the
complete message before choosing to send it through Gmail.

## 🚀 Get started

Install [Quarto](https://quarto.org/docs/get-started/) 1.4 or later before you
begin. A quarto-mail workspace is an ordinary Quarto project. Rendering is
always safe: it writes files locally and never sends mail. Running the
generated `gog` command is the step that sends the message.

### 1. Create a mail project

Create an empty directory and apply the starter template:

```sh
mkdir my-mail
cd my-mail
quarto use template mavam/quarto-mail --no-prompt
```

The template installs the extension locally and creates a working message:

```text
my-mail.qmd
_quarto.yml
_metadata.yml
_extensions/
```

If you already have a Quarto project, install only the extension instead:

```sh
quarto add mavam/quarto-mail
```

Then add `mail-profiles` to the project's shared metadata and create a `.qmd`
file using the format shown later.

### 2. Configure your profiles

Edit `_metadata.yml` and replace the example values with your Gmail accounts
and sign-off identities:

```yaml
mail-profiles:
  senders:
    personal:
      account: user@example.com
      from: user@example.com
  identities:
    personal:
      name: Alex
```

The `account` must identify an account already authenticated with `gog`. The
`from` address may be that account or one of its configured aliases. When both
addresses match, Quarto Mail lets `gog` use the account's primary sender name.
For an alias, Gmail's matching send-as configuration supplies the name.

### 3. Write your first message

Rename the starter document and edit its front matter and Markdown body:

```sh
mv my-mail.qmd hello.qmd
```

```yaml
---
format: mail-html
mail:
  sender: personal
  opening: Hi Jane,
  identity: personal
  closing: Best,
  to:
    - Jane Doe <jane@example.com>
  cc: []
  bcc: []
  subject: Hello
  attachments: []
---

This is the message body in Markdown.
```

Each `.qmd` represents one email. Its optional `opening` supplies a single-line
greeting before the Markdown body; omit it when the message should begin
directly with its content. The message selects reusable profiles from Quarto's
shared metadata, while its complete recipient lists remain explicit. Use
standard mailbox notation to preserve display names, for example,
`Recipient Name <recipient@example.com>`.

### 4. Render and review

Render the message without sending it:

```sh
quarto render hello.qmd
```

This creates an HTML preview and the exact transport artifacts:

```text
hello.html
hello.mail/
├── manifest.json
├── body.txt
└── body.html
```

The extension supports three output formats:

- `mail-html` creates the browser preview shown above.
- `mail-plain` emits the exact plain-text body, for example with
  `quarto render hello.qmd --to mail-plain`.
- `mail-gog` emits a reviewable shell command that sends both body variants.

Every format also refreshes the same `.mail/` bundle. Review all parts of the
message:

```sh
cat hello.mail/manifest.json
cat hello.mail/body.txt
```

Open `hello.html` in a browser. The manifest contains the sender, recipients,
subject, reply information, and attachments. The bundle contains the exact
plain-text and HTML bodies.

### 5. Prepare and send

Install and authenticate [`gog`](https://github.com/steipete/gogcli) before
sending. Then render the `mail-gog` format to a shell script:

```sh
quarto render hello.qmd --to mail-gog --output - > /tmp/send-hello.sh
```

Inspect the generated command and the newly rendered bundle:

```sh
cat /tmp/send-hello.sh
cat hello.mail/manifest.json
cat hello.mail/body.txt
```

Open `hello.mail/body.html` in a browser. If you change anything, regenerate
the script and review the complete message again. Execute the reviewed script
to send exactly once:

```sh
sh /tmp/send-hello.sh
```

`gog` prints the Gmail API result as JSON. Keep or delete the source and
rendered artifacts according to your own mail-draft workflow.

## ✨ More workflows

### Reply to an email

Keep every recipient explicit and add the Gmail message ID. You may omit
`subject` to inherit it from the original message:

```yaml
mail:
  sender: personal
  identity: personal
  closing: Best,
  to:
    - Original Sender <original-sender@example.com>
  cc:
    - Other Participant <participant@example.com>
  bcc: []
  attachments: []
  reply-to-message-id: MESSAGE_ID
  quote: true
```

A new message must specify `subject`; a reply may omit it or provide a
replacement. Set `quote: true` to include the original message.

### Attach files

List attachment paths relative to the `.qmd` file:

```yaml
mail:
  attachments:
    - files/report.pdf
    - images/diagram.png
```

Rendering validates every attachment path before sending.

## ⚙️ Configuration

### Configure senders and sign-off identities

Define reusable profiles in `_metadata.yml` as ordinary Quarto shared metadata:

```yaml
mail-profiles:
  senders:
    personal:
      account: user@example.com
      from: user@example.com
    work:
      account: work@example.com
      from: alias@example.com

  identities:
    personal:
      name: Alex
    formal:
      name: Alex Example
      indent: 4
    work:
      name: Alex Example
```

You can also define these profiles in `_quarto.yml` or in files listed under
its standard `metadata-files` option. Quarto's normal metadata merging rules
apply.

A sender controls the authenticated account and the address in the `From`
header. Keep both values as bare email addresses. When they match, the generated
command omits `--from`, preserving the primary sender name that plain `gog` uses.
For a configured alias, the command passes `--from` and Gmail applies that
alias's send-as name. An identity is the name placed directly after the closing:

```text
Best,

Alex
```

Select profiles independently in each message:

```yaml
mail:
  sender: work
  identity: work
```

The optional identity `indent` sets the number of spaces before the name and
defaults to `0`. The message-level components compose as `opening`, Markdown
content, `closing`, `identity`, and `signature`. Each component is independent:
omit `opening` for no greeting, omit `closing` to sign with the identity alone,
or omit `identity` when the message should not add a sign-off name.

### Add a signature

A signature is an optional block after the sign-off identity. Define its
plain-text representation in `_metadata.yml`:

```yaml
mail-profiles:
  signatures:
    work:
      plain: |-
        Alex Example
        Role
        Example Organization
```

Select it in a message:

```yaml
mail:
  signature: work
```

The resulting text follows the conventional email signature format. The `␠`
symbol makes the required trailing space in the separator visible:

```text
Best,

Alex Example

--␠
Alex Example
Role
Example Organization
```

Signature profiles may set `indent`, which defaults to `0`. Here, *signature*
means a conventional email signature block, not a cryptographic signature.
Gmail signature settings aren't applied.

### Add a rich HTML signature

Add an inline `html` fragment when a signature needs tables, links, inline
styles, or images:

```yaml
mail-profiles:
  signatures:
    work:
      plain: |-
        Alex Example
        Role
        Example Organization
      html: |-
        <table role="presentation"><tr><td><img src="https://example.com/logo.png" alt="Example Organization"></td><td><strong>Alex Example</strong><br>Role</td></tr></table>
```

The required `plain` field provides the plain-text signature, while the optional
`html` field provides a trusted rich fragment. Keep the fragment on one physical
line because metadata line breaks become HTML line breaks. Use inline styles and
absolute HTTPS URLs for hosted images. Local image paths aren't supported. When
`html` is present, `indent` affects only the plain-text signature.

Rendering rejects malformed recipients, missing profiles, invalid indentation,
and inline images in the authored Markdown body.

## 🧰 Requirements

- Quarto 1.4 or later.
- Optional: `gog` to send email with the `mail-gog` format.

## 📄 License

[MIT](LICENSE)
