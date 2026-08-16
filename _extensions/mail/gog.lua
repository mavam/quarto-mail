local function fail(message)
  assert(false, "quarto-mail: " .. message)
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

local function bundle_path()
  local source = source_path()
  local directory = pandoc.path.directory(source)
  local filename = pandoc.path.filename(source)
  local stem = filename:gsub("%.[^%.]+$", "")
  return pandoc.path.join({ directory, stem .. ".mail" })
end

local function read_manifest(directory)
  local path = pandoc.path.join({ directory, "manifest.json" })
  local handle, message = io.open(path, "rb")
  if handle == nil then
    fail("cannot read " .. path .. ": " .. message)
  end
  local contents = handle:read("*a")
  handle:close()
  return quarto.json.decode(contents)
end

local function shell_quote(value)
  return "'" .. value:gsub("'", "'\"'\"'") .. "'"
end

local function gog_command(manifest, directory)
  local lines = {
    "gog --account " .. shell_quote(manifest.account) .. " gmail send",
    "--from " .. shell_quote(manifest.from),
  }
  if manifest.reply_to_message_id ~= nil then
    table.insert(lines, "--reply-to-message-id " .. shell_quote(manifest.reply_to_message_id))
  end
  table.insert(lines, "--to " .. shell_quote(table.concat(manifest.to, ",")))
  if #manifest.cc > 0 then
    table.insert(lines, "--cc " .. shell_quote(table.concat(manifest.cc, ",")))
  end
  if #manifest.bcc > 0 then
    table.insert(lines, "--bcc " .. shell_quote(table.concat(manifest.bcc, ",")))
  end
  if manifest.subject ~= nil then
    table.insert(lines, "--subject " .. shell_quote(manifest.subject))
  end
  if manifest.quote then
    table.insert(lines, "--quote")
  end
  table.insert(lines, "--body-file " .. shell_quote(pandoc.path.join({ directory, manifest.body_text })))
  table.insert(lines, "--body-html-file " .. shell_quote(pandoc.path.join({ directory, manifest.body_html })))
  for _, attachment in ipairs(manifest.attachments) do
    table.insert(lines, "--attach " .. shell_quote(attachment))
  end
  table.insert(lines, "--no-input")
  table.insert(lines, "--json")
  return table.concat(lines, " \\\n  ") .. "\n"
end

function Writer(_document, _options)
  local directory = bundle_path()
  return gog_command(read_manifest(directory), directory)
end
