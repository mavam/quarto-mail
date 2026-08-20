local function fail(message)
  assert(false, "quarto-mail: " .. message)
end

local function stringify(value)
  return pandoc.utils.stringify(value)
end

local function scalar(meta, key, required, path)
  local value = meta[key]
  local display_path = path or key
  if value == nil then
    if required then
      fail("missing required metadata field '" .. display_path .. "'")
    end
    return nil
  end
  local result = stringify(value)
  if result == "" then
    fail("metadata field '" .. display_path .. "' must not be empty")
  end
  if result:find("[\r\n]") then
    fail("metadata field '" .. display_path .. "' must be a single line")
  end
  return result
end

local function mailbox_string(value)
  if type(value) ~= "table" then
    return stringify(value)
  end
  local inlines = {}
  for _, inline in ipairs(value) do
    if inline.tag == "Link" and inline.target:match("^mailto:") then
      table.insert(inlines, pandoc.Str("<" .. inline.target:sub(8) .. ">"))
    else
      table.insert(inlines, inline)
    end
  end
  return stringify(inlines)
end

local function string_list(meta, key, required, path, converter)
  local value = meta[key]
  local display_path = path or key
  local convert = converter or stringify
  if value == nil then
    if required then
      fail("missing required metadata field '" .. display_path .. "'")
    end
    return {}
  end
  if type(value) ~= "table" then
    fail("metadata field '" .. display_path .. "' must be a list")
  end
  local result = {}
  for _, item in ipairs(value) do
    local text = convert(item)
    if text == "" then
      fail("metadata field '" .. display_path .. "' must not contain empty values")
    end
    if text:find("[\r\n]") then
      fail("metadata field '" .. display_path .. "' must contain single-line values")
    end
    table.insert(result, text)
  end
  if required and #result == 0 then
    fail("metadata field '" .. display_path .. "' must contain at least one value")
  end
  return result
end

local function boolean(meta, key, default, path)
  local value = meta[key]
  local display_path = path or key
  if value == nil then
    return default
  end
  if type(value) == "boolean" then
    return value
  end
  local text = stringify(value)
  if text == "true" then
    return true
  elseif text == "false" then
    return false
  end
  fail("metadata field '" .. display_path .. "' must be true or false")
end

local function profile(root, group, name)
  local profiles = root[group]
  if profiles == nil or type(profiles) ~= "table" then
    fail("missing profile group 'mail-profiles." .. group .. "'")
  end
  local result = profiles[name]
  if result == nil or type(result) ~= "table" then
    local labels = {
      senders = "sender",
      identities = "identity",
      signatures = "signature",
    }
    fail("unknown " .. labels[group] .. " profile '" .. name .. "'")
  end
  return result
end

local function profile_scalar(value, path, required)
  if value == nil then
    if required then
      fail("missing profile field '" .. path .. "'")
    end
    return nil
  end
  local result = stringify(value)
  if required and result == "" then
    fail("profile field '" .. path .. "' must not be empty")
  end
  if result:find("[\r\n]") then
    fail("profile field '" .. path .. "' must be a single line")
  end
  return result
end

local function multiline_string(value)
  if type(value) ~= "table" or pandoc.utils.type(value) ~= "Inlines" then
    return stringify(value)
  end
  local parts = {}
  for _, inline in ipairs(value) do
    if inline.tag == "Space" then
      table.insert(parts, " ")
    elseif inline.tag == "SoftBreak" or inline.tag == "LineBreak" then
      table.insert(parts, "\n")
    elseif inline.tag == "Str" or inline.tag == "Code" or inline.tag == "RawInline" then
      table.insert(parts, inline.text)
    else
      table.insert(parts, stringify(inline))
    end
  end
  return table.concat(parts)
end

local function profile_content(value, path, required)
  if value == nil then
    if required then
      fail("missing profile field '" .. path .. "'")
    end
    return nil
  end
  local result = multiline_string(value):gsub("\r\n", "\n"):gsub("\r", "\n")
  result = result:gsub("\n+$", "")
  if result == "" then
    fail("profile field '" .. path .. "' must not be empty")
  end
  return result
end

local function profile_html(value, path)
  if value == nil then
    return nil
  end
  if multiline_string(value) == "" then
    fail("profile field '" .. path .. "' must not be empty")
  end
  local value_type = pandoc.utils.type(value)
  local result
  if value_type == "Inlines" then
    result = pandoc.write(
      pandoc.Pandoc({ pandoc.Plain(value) }),
      "html",
      { wrap_text = "none" }
    )
  elseif value_type == "Blocks" then
    result = pandoc.write(pandoc.Pandoc(value), "html", { wrap_text = "none" })
  else
    result = stringify(value)
  end
  return result:gsub("\n+$", "")
end

local function profile_indent(value, path)
  if value == nil then
    return 0
  end
  local number = tonumber(stringify(value))
  if number == nil or number < 0 or number % 1 ~= 0 then
    fail("profile field '" .. path .. "' must be a non-negative integer")
  end
  return number
end

local function absolute_path(path)
  return path:sub(1, 1) == "/" or path:match("^%a:[/\\]") ~= nil
end

local function source_path()
  local source = quarto ~= nil and quarto.doc ~= nil and quarto.doc.input_file or nil
  if source == nil or source == "" then
    source = PANDOC_STATE.input_files[1]
  end
  if source == nil or source == "" then
    fail("cannot determine the source document path")
  end
  if not absolute_path(source) then
    source = pandoc.path.join({ pandoc.system.get_working_directory(), source })
  end
  return pandoc.path.normalize(source)
end

local function resolve_file(path, directory, label)
  local resolved = path
  if not absolute_path(resolved) then
    resolved = pandoc.path.join({ directory, resolved })
  end
  resolved = pandoc.path.normalize(resolved)
  local handle = io.open(resolved, "rb")
  if handle == nil then
    fail(label .. " does not exist or is not readable: " .. path)
  end
  handle:close()
  return resolved
end

local function resolve_attachments(attachments, directory)
  local result = {}
  for _, attachment in ipairs(attachments) do
    table.insert(result, resolve_file(attachment, directory, "attachment"))
  end
  return result
end

local image_types = {
  png = "image/png",
  jpg = "image/jpeg",
  jpeg = "image/jpeg",
  gif = "image/gif",
  webp = "image/webp",
  svg = "image/svg+xml",
}

local function collect_inline_images(document, directory)
  local images = {}
  local by_source = {}
  document:walk({
    Image = function(image)
      local target = image.src
      local lowered_target = target:lower()
      if lowered_target:match("^https://") then
        return image
      end
      if not absolute_path(target) and
          (target:match("^%a[%w+.-]*:") or target:match("^//")) then
        fail("unsupported inline image URL '" .. target .. "'; use a local path or HTTPS URL")
      end
      local source = resolve_file(target, directory, "inline image")
      local extension = source:match("%.([^./\\]+)$")
      extension = extension ~= nil and extension:lower() or ""
      local content_type = image_types[extension]
      if content_type == nil then
        fail("unsupported inline image format for '" .. target ..
          "'; supported formats are PNG, JPEG, GIF, WebP, and SVG")
      end
      if by_source[source] == nil then
        local item = {
          source = source,
          filename = pandoc.path.filename(source),
          content_type = content_type,
          content_id = "image-" .. tostring(#images + 1) .. "@quarto-mail",
        }
        by_source[source] = item
        table.insert(images, item)
      end
      return image
    end,
  })
  return images, by_source
end

local function text_inlines(text)
  return { pandoc.Str(text) }
end

local function identity_block(name, indent)
  local prefix = string.rep("\u{00a0}", indent)
  return pandoc.Div({ pandoc.Para(text_inlines(prefix .. name)) })
end

local function signature_block(plain, indent, html)
  local blocks = {}
  if html ~= nil then
    table.insert(blocks, pandoc.RawBlock("html", html))
  else
    local prefix = string.rep("\u{00a0}", indent)
    local inlines = {}
    local index = 0
    for line in (plain .. "\n"):gmatch("(.-)\n") do
      if index > 0 then
        table.insert(inlines, pandoc.LineBreak())
      end
      table.insert(inlines, pandoc.Str(prefix .. line))
      index = index + 1
    end
    table.insert(blocks, pandoc.Div({ pandoc.Plain(inlines) }))
  end
  return pandoc.Div(blocks)
end

local function div_has_class(div, class_name)
  for _, class in ipairs(div.classes) do
    if class == class_name then
      return true
    end
  end
  return false
end

local function link_for_plain_text(link)
  local label = stringify(link.content)
  local target = link.target
  if target == "" or label == target then
    return link.content
  end
  local result = {}
  for _, inline in ipairs(link.content) do
    table.insert(result, inline)
  end
  table.insert(result, pandoc.Space())
  table.insert(result, pandoc.Str("<" .. target .. ">"))
  return result
end

local function write_file(path, contents)
  local handle, message = io.open(path, "wb")
  if handle == nil then
    fail("cannot write " .. path .. ": " .. message)
  end
  handle:write(contents)
  handle:close()
end

local function read_file(path)
  local handle, message = io.open(path, "rb")
  if handle == nil then
    fail("cannot read " .. path .. ": " .. message)
  end
  local contents = handle:read("*a")
  handle:close()
  return contents
end

local final_artifacts = {
  "message.eml",
  "gmail-request.json",
  "gmail-draft-request.json",
  "reply.json",
  "prepare.sh",
}

local function remove_final_artifacts(directory)
  for _, name in ipairs(final_artifacts) do
    os.remove(pandoc.path.join({ directory, name }))
  end
end

local function source_mail_metadata(source)
  local contents = read_file(source)
  local parsed = pandoc.read(contents, "markdown-smart-subscript")
  return parsed.meta.mail
end

local function html_escape(value)
  return value:gsub("&", "&amp;")
    :gsub('"', "&quot;")
    :gsub("<", "&lt;")
    :gsub(">", "&gt;")
end

local function render_block_html(block)
  if block.tag == "Para" or block.tag == "Plain" then
    local html = pandoc.write(
      pandoc.Pandoc({ pandoc.Plain(block.content) }),
      "html",
      { wrap_text = "none" }
    ):gsub("\n+$", "")
    return "<div>" .. html .. "</div>"
  end
  return pandoc.write(
    pandoc.Pandoc({ block }),
    "html",
    { wrap_text = "none" }
  ):gsub("\n+$", "")
end

local function transport_blocks(message_blocks, inline_images, source_directory)
  return pandoc.Pandoc(message_blocks):walk({
    Image = function(image)
      if not image.src:lower():match("^https://") then
        local source = image.src
        if not absolute_path(source) then
          source = pandoc.path.join({ source_directory, source })
        end
        source = pandoc.path.normalize(source)
        local inline_image = inline_images[source]
        if inline_image == nil then
          fail("cannot match inline image to its resolved source: " .. image.src)
        end
        image.src = "cid:" .. inline_image.content_id
      end
      return image
    end,
  }).blocks
end

local function render_email_html(
    message_blocks,
    opening,
    closing,
    identity,
    identity_indent,
    signature_plain,
    signature_indent,
    signature_html
  )
  local sections = {}
  if opening ~= nil then
    table.insert(sections, {
      html = "<div>" .. html_escape(opening) .. "</div>",
      native_spacing = false,
    })
  end
  for _, block in ipairs(message_blocks) do
    table.insert(sections, {
      html = render_block_html(block),
      native_spacing = block.tag == "BulletList" or block.tag == "OrderedList",
    })
  end
  if closing ~= nil then
    table.insert(sections, {
      html = "<div>" .. html_escape(closing) .. "</div>",
      native_spacing = false,
    })
  end
  if identity ~= nil then
    table.insert(sections, {
      html = "<div>" .. string.rep("&nbsp;", identity_indent) ..
        html_escape(identity) .. "</div>",
      native_spacing = false,
    })
  end
  if signature_plain ~= nil then
    local html = signature_html
    if html == nil then
      local prefix = string.rep("&nbsp;", signature_indent)
      html = prefix .. html_escape(signature_plain):gsub("\n", "<br>" .. prefix)
    end
    table.insert(sections, {
      html = "<div>" .. html .. "</div>",
      native_spacing = false,
    })
  end
  local html = {}
  for index, section in ipairs(sections) do
    local previous = sections[index - 1]
    if previous ~= nil and
        not previous.native_spacing and
        not section.native_spacing then
      table.insert(html, "<div><br></div>")
    end
    table.insert(html, section.html)
  end
  return "<div>\n" .. table.concat(html, "\n") .. "\n</div>\n"
end

local function render_document(document, source, source_directory, bundle_directory)
  local mail = source_mail_metadata(source)
  if mail == nil or type(mail) ~= "table" then
    fail("missing required metadata field 'mail'")
  end
  local profiles = document.meta["mail-profiles"]
  if profiles == nil or type(profiles) ~= "table" then
    fail("missing required metadata field 'mail-profiles'")
  end
  local sender_name = scalar(mail, "sender", true, "mail.sender")
  local identity_name = scalar(mail, "identity", false, "mail.identity")
  local signature_name = scalar(mail, "signature", false, "mail.signature")
  local reply_all = boolean(mail, "reply-all", false, "mail.reply-all")
  local to = string_list(mail, "to", not reply_all, "mail.to", mailbox_string)
  local cc = string_list(mail, "cc", false, "mail.cc", mailbox_string)
  local bcc = string_list(mail, "bcc", false, "mail.bcc", mailbox_string)
  local subject = scalar(mail, "subject", false, "mail.subject")
  local opening = scalar(mail, "opening", false, "mail.opening")
  local closing = scalar(mail, "closing", false, "mail.closing")
  local attachments = string_list(mail, "attachments", false, "mail.attachments")
  local reply_to_message_id = scalar(
    mail,
    "reply-to-message-id",
    false,
    "mail.reply-to-message-id"
  )
  local forward_message_id = scalar(mail, "forward-message-id", false, "mail.forward-message-id")
  local quote = boolean(mail, "quote", false, "mail.quote")
  local include_original_attachments = boolean(mail, "include-original-attachments", true, "mail.include-original-attachments")
  local delivery = scalar(mail, "delivery", false, "mail.delivery") or "send"
  local draft_id = scalar(mail, "draft-id", false, "mail.draft-id")

  if reply_to_message_id ~= nil and forward_message_id ~= nil then fail("reply and forward IDs are mutually exclusive") end
  if reply_all and reply_to_message_id == nil then fail("mail.reply-all requires 'mail.reply-to-message-id'") end
  if delivery ~= "send" and delivery ~= "draft" then fail("mail.delivery must be 'send' or 'draft'") end
  if draft_id ~= nil and delivery ~= "draft" then fail("mail.draft-id requires mail.delivery: draft") end
  if subject == nil and reply_to_message_id == nil and forward_message_id == nil then
    fail("missing required metadata field 'mail.subject' for a new message")
  end
  if quote and reply_to_message_id == nil and forward_message_id == nil then
    fail("mail.quote requires 'mail.reply-to-message-id'")
  end
  local sender = profile(profiles, "senders", sender_name)
  local account = profile_scalar(
    sender.account,
    "mail-profiles.senders." .. sender_name .. ".account",
    true
  )
  local from = profile_scalar(
    sender.from,
    "mail-profiles.senders." .. sender_name .. ".from",
    true
  )
  local from_name = profile_scalar(
    sender.name,
    "mail-profiles.senders." .. sender_name .. ".name",
    false
  )
  local resolved_identity = nil
  local identity_indent = 0
  local signature_plain = nil
  local signature_indent = 0
  local signature_html = nil
  if identity_name ~= nil then
    local identity = profile(profiles, "identities", identity_name)
    resolved_identity = profile_scalar(
      identity.name,
      "mail-profiles.identities." .. identity_name .. ".name",
      true
    )
    identity_indent = profile_indent(
      identity.indent,
      "mail-profiles.identities." .. identity_name .. ".indent"
    )
  end
  if from_name == nil then
    from_name = resolved_identity
  end
  if signature_name ~= nil then
    local signature = profile(profiles, "signatures", signature_name)
    signature_plain = profile_content(
      signature.plain,
      "mail-profiles.signatures." .. signature_name .. ".plain",
      true
    )
    signature_indent = profile_indent(
      signature.indent,
      "mail-profiles.signatures." .. signature_name .. ".indent"
    )
    signature_html = profile_html(
      signature.html,
      "mail-profiles.signatures." .. signature_name .. ".html"
    )
  end

  document = document:walk({
    Div = function(div)
      if div_has_class(div, "hidden") and #div.content == 0 then
        return {}
      end
      return div
    end,
  })

  local message_blocks = document.blocks
  local inline_images, inline_images_by_source = collect_inline_images(document, source_directory)
  local blocks = {}
  if opening ~= nil then
    table.insert(blocks, pandoc.Div({ pandoc.Para(text_inlines(opening)) }))
  end
  for _, block in ipairs(document.blocks) do
    table.insert(blocks, block)
  end
  if closing ~= nil then
    table.insert(blocks, pandoc.Div({ pandoc.Para(text_inlines(closing)) }))
  end
  if resolved_identity ~= nil then
    table.insert(blocks, identity_block(resolved_identity, identity_indent))
  end
  if signature_plain ~= nil then
    table.insert(blocks, signature_block(signature_plain, signature_indent, signature_html))
  end
  document.blocks = blocks

  local resolved_attachments = resolve_attachments(attachments, source_directory)

  local identity_text = nil
  if resolved_identity ~= nil then
    identity_text = string.rep(" ", identity_indent) .. resolved_identity
  end
  local signature_text = nil
  if signature_plain ~= nil then
    local prefix = string.rep(" ", signature_indent)
    signature_text = prefix .. signature_plain:gsub("\n", "\n" .. prefix)
  end
  local text_blocks = {}
  if opening ~= nil then
    table.insert(text_blocks, pandoc.Para(text_inlines(opening)))
  end
  for _, block in ipairs(message_blocks) do
    table.insert(text_blocks, block)
  end
  if closing ~= nil then
    table.insert(text_blocks, pandoc.Para(text_inlines(closing)))
  end
  if identity_text ~= nil then
    table.insert(text_blocks, pandoc.RawBlock("plain", identity_text))
  end
  if signature_text ~= nil then
    table.insert(text_blocks, pandoc.RawBlock("plain", "\n-- \n" .. signature_text))
  end
  local text_document = pandoc.Pandoc(text_blocks, document.meta):walk({
    Link = link_for_plain_text,
  })
  local body_text = pandoc.write(text_document, "plain", { wrap_text = "none" })
  local body_html = render_email_html(
    transport_blocks(message_blocks, inline_images_by_source, source_directory),
    opening,
    closing,
    resolved_identity,
    identity_indent,
    signature_plain,
    signature_indent,
    signature_html
  )
  local values = {
    source = source,
    account = account,
    from = from,
    from_name = from_name,
    to = to,
    cc = cc,
    bcc = bcc,
    subject = subject,
    body_text = "body.txt",
    body_html = "body.html",
    attachments = resolved_attachments,
    inline_images = inline_images,
    reply_to_message_id = reply_to_message_id,
    forward_message_id = forward_message_id,
    reply_all = reply_all,
    include_original_attachments = include_original_attachments,
    delivery = delivery,
    draft_id = draft_id,
  }
  if reply_to_message_id ~= nil or forward_message_id ~= nil then
    values.quote = quote
  end

  pandoc.system.make_directory(bundle_directory, true)
  write_file(pandoc.path.join({ bundle_directory, "body.txt" }), body_text)
  write_file(pandoc.path.join({ bundle_directory, "body.html" }), body_html)
  write_file(
    pandoc.path.join({ bundle_directory, "manifest.json" }),
    quarto.json.encode(values) .. "\n"
  )
  local script_directory = pandoc.path.directory(PANDOC_SCRIPT_FILE)
  local ok, code, _output, error_output = pcall(
    pandoc.system.command,
    "python3",
    {
      pandoc.path.join({ script_directory, "mime.py" }),
      "render",
      bundle_directory,
    }
  )
  if not ok then
    remove_final_artifacts(bundle_directory)
    fail("cannot run Python 3 MIME builder: " .. tostring(code))
  end
  if code ~= false and code ~= 0 then
    remove_final_artifacts(bundle_directory)
    local detail = error_output ~= nil and error_output:gsub("%s+$", "") or ""
    if detail == "" then
      detail = "exit status " .. tostring(code)
    end
    fail("MIME builder failed: " .. detail)
  end

  return document
end

function Pandoc(document)
  local source = source_path()
  local source_directory = pandoc.path.directory(source)
  local filename = pandoc.path.filename(source)
  local stem = filename:gsub("%.[^%.]+$", "")
  local bundle_directory = pandoc.path.join({ source_directory, stem .. ".mail" })
  local succeeded, result = pcall(
    render_document,
    document,
    source,
    source_directory,
    bundle_directory
  )
  if not succeeded then
    remove_final_artifacts(bundle_directory)
    error(result, 0)
  end
  return result
end
