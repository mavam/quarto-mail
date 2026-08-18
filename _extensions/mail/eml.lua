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

function Writer(_document, _options)
  local source = source_path()
  local stem = pandoc.path.filename(source):gsub("%.[^%.]+$", "")
  local bundle = pandoc.path.join({ pandoc.path.directory(source), stem .. ".mail" })
  local manifest = quarto.json.decode(read_file(pandoc.path.join({ bundle, "manifest.json" })))
  local message = pandoc.path.join({ bundle, "message.eml" })
  local handle = io.open(message, "rb")
  if handle == nil and manifest.reply_to_message_id ~= nil then
    fail("reply artifacts are not prepared; run " ..
      pandoc.path.join({ bundle, "prepare.sh" }))
  elseif handle == nil then
    fail("cannot read " .. message)
  end
  handle:close()
  return read_file(message)
end
