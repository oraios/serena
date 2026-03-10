## utils.nim: String and sequence utility functions for testing LSP features

proc trim*(s: string): string =
  ## Remove leading and trailing whitespace
  var start = 0
  var stop = s.len - 1
  while start <= stop and s[start] == ' ':
    inc start
  while stop >= start and s[stop] == ' ':
    dec stop
  s[start..stop]

proc startsWith*(s, prefix: string): bool =
  ## Check if string s starts with prefix
  if prefix.len > s.len:
    return false
  for i in 0..<prefix.len:
    if s[i] != prefix[i]:
      return false
  true

proc endsWith*(s, suffix: string): bool =
  ## Check if string s ends with suffix
  if suffix.len > s.len:
    return false
  let offset = s.len - suffix.len
  for i in 0..<suffix.len:
    if s[offset + i] != suffix[i]:
      return false
  true

proc split*(s, sep: string): seq[string] =
  ## Split string s by separator sep
  var parts: seq[string] = @[]
  var start = 0
  var i = 0
  while i <= s.len - sep.len:
    if s[i..i+sep.len-1] == sep:
      parts.add(s[start..i-1])
      start = i + sep.len
      i = start
    else:
      inc i
  parts.add(s[start..s.len-1])
  parts

proc join*(parts: seq[string], sep: string): string =
  ## Join sequence of strings with separator
  var result = ""
  for i, part in parts:
    if i > 0:
      result = result & sep
    result = result & part
  result
