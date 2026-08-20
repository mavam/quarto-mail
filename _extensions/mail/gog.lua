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

function Writer(_document, _options)
  local directory = bundle_path()
  local manifest = read_manifest(directory)
  local request = pandoc.path.join({ directory, "gmail-request.json" })
  local preparation = pandoc.path.join({ directory, "prepare.sh" })
  local missing_message
  if manifest.reply_to_message_id ~= nil then
    missing_message = "reply artifacts are not prepared; run " .. preparation
  elseif manifest.forward_message_id ~= nil then
    missing_message = "forward artifacts are not prepared; run " .. preparation
  else
    missing_message = "Gmail request is missing; render the message again"
  end
  local method = "gmail.users.messages.send"
  local params = '{"userId":"me"}'
  local body = request
  if manifest.delivery == "draft" then
    method = "gmail.users.drafts.create"
    body = pandoc.path.join({ directory, "gmail-draft-request.json" })
    if manifest.draft_id ~= nil then
      method = "gmail.users.drafts.update"
      params = '{"userId":"me","id":"' .. manifest.draft_id .. '"}'
    end
  end
  return "test -f " .. shell_quote(body) .. " || { printf '%s\\n' " ..
    shell_quote("quarto-mail: " .. missing_message) .. " >&2; exit 1; }\n" ..
    "gog --account " .. shell_quote(manifest.account) ..
    " api call gmail v1 " .. method .. " \\\n  --params " .. shell_quote(params) .. " \\\n  --body @" .. shell_quote(body) ..
    " \\\n  --allow-write --force --no-input\n"
end
