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

local function read_file(path)
  local handle, message = io.open(path, "rb")
  if handle == nil then
    fail("cannot read " .. path .. ": " .. message)
  end
  local contents = handle:read("*a")
  handle:close()
  return contents
end

local function shell_quote(value)
  return "'" .. value:gsub("'", "'\"'\"'") .. "'"
end

function Writer(_document, _options)
  local source = source_path()
  local stem = pandoc.path.filename(source):gsub("%.[^%.]+$", "")
  local bundle = pandoc.path.join({ pandoc.path.directory(source), stem .. ".mail" })
  local manifest = quarto.json.decode(read_file(pandoc.path.join({ bundle, "manifest.json" })))
  if manifest.reply_to_message_id ~= nil then
    fail("mail-gmail does not support replies; use mail-gog")
  end
  local request = pandoc.path.join({ bundle, "gmail-request.json" })
  read_file(request)
  return "gog --account " .. shell_quote(manifest.account) ..
    " api call gmail v1 gmail.users.messages.send \\\n  --params '{\"userId\":\"me\"}' \\\n  --body @" .. shell_quote(request) ..
    " \\\n  --allow-write --force --no-input\n"
end
