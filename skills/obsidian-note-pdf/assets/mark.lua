-- Convert Pandoc's ==mark== spans into lua-ul highlights that support CJK
-- line breaking.  The coloured emoji used by the Obsidian note select a
-- print-friendly highlight colour and are removed from the text.
local marker_colors = {
  ["🟡"] = "hlYellow",
  ["🔴"] = "hlRed",
  ["🔵"] = "hlBlue",
}

local function clean_marker(inlines)
  local color = "hlYellow"
  local out = {}
  for _, inline in ipairs(inlines) do
    if inline.t == "Str" then
      local s = inline.text
      for marker, c in pairs(marker_colors) do
        if s:find(marker, 1, true) then
          color = c
        end
        s = s:gsub(marker, "")
      end
      if s ~= "" then
        out[#out + 1] = pandoc.Str(s)
      end
    else
      out[#out + 1] = inline
    end
  end
  return color, out
end

function Span(el)
  if el.classes:includes("mark") then
    local color, content = clean_marker(el.content)
    local result = {
      pandoc.RawInline("latex", "\\highLight[" .. color .. "]{"),
    }
    for _, inline in ipairs(content) do
      result[#result + 1] = inline
    end
    result[#result + 1] = pandoc.RawInline("latex", "}")
    return result
  end
end
