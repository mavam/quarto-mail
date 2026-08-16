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

local function body_path()
  local source = source_path()
  local directory = pandoc.path.directory(source)
  local filename = pandoc.path.filename(source)
  local stem = filename:gsub("%.[^%.]+$", "")
  return pandoc.path.join({ directory, stem .. ".mail", "body.txt" })
end

function Writer(_document, _options)
  local path = body_path()
  local handle, message = io.open(path, "rb")
  if handle == nil then
    fail("cannot read " .. path .. ": " .. message)
  end
  local contents = handle:read("*a")
  handle:close()
  return (contents:gsub("\n$", ""))
end
