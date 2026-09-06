Email previews now group the subject, recipients, and attachments along a compact open spine. Circled CC/BCC badges and shorter attachment labels keep the review focused, without changing the outgoing message.

## 🔧 Changes

### Compact email approval previews

Email approval previews now use an open spine: glyphs share one column, with a vertical spacer between the subject, recipients, and attachments. Each recipient and attachment has its own row, with circled badges for CC and BCC:

```text
≡ Project kickoff
│
→ Jane Doe <jane@example.com>
⇢ Grace Park <grace@example.com> Ⓒ
◌ archive@example.com Ⓑ
│
⊕ project-brief.pdf · PDF · 248 KB
```

The fixed layout omits the sender, sending account, empty groups, and normal send operation, without adding preview settings. Attachment types use short labels such as `PDF`, `TXT`, and `XLSX`, with human-readable sizes. Distinct Reply-To addresses, draft operations, and inline attachments remain visible. Addresses display literally in Markdown, and the outgoing message and delivery script remain unchanged.

*By @mavam in #10.*
