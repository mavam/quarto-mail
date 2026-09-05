local function fail(message)
  assert(false, "quarto-mail: " .. message)
end

function Writer(_document, _options)
  local source = quarto.doc.input_file
  if source:sub(1, 1) ~= "/" and not source:match("^%a:[/\\]") then
    source = pandoc.path.join({ pandoc.system.get_working_directory(), source })
  end
  local stem = pandoc.path.filename(source):gsub("%.[^%.]+$", "")
  local script = pandoc.path.join({ pandoc.path.directory(source), stem .. ".send.sh" })
  local output = PANDOC_STATE.output_file
  if output ~= nil and output ~= "-" then
    if output:sub(1, 1) ~= "/" and not output:match("^%a:[/\\]") then
      output = pandoc.path.join({ pandoc.system.get_working_directory(), output })
    end
    if pandoc.path.normalize(output) == pandoc.path.normalize(script) then
      fail("--output controls the preview and must not overwrite the delivery script; use --output -")
    end
  end
  os.remove(script)
  local bundle = pandoc.path.join({ pandoc.path.directory(source), stem .. ".mail" })
  local helper = pandoc.path.join({ pandoc.path.directory(PANDOC_SCRIPT_FILE), "delivery.py" })
  local ok, code, result, error_output = pcall(pandoc.system.command, "python3", { helper, bundle })
  if not ok then
    fail("cannot build delivery script: " .. tostring(code))
  end
  if code ~= false and code ~= 0 then
    fail("cannot build delivery script: " .. (error_output or tostring(code)))
  end
  return result
end
