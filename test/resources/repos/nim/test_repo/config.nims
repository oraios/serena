# Nim configuration file

switch("path", "$projectDir/../src")
switch("warning", "UnusedImport:off")

when defined(release):
  switch("opt", "speed")
  switch("checks", "off")
  switch("assertions", "off")
else:
  switch("opt", "none")
  switch("checks", "on")
  switch("assertions", "on")

task test, "Run tests":
  exec "nim c -r tests/test_main.nim"

task build, "Build the project":
  exec "nim c -d:release main.nim"

task clean, "Clean build artifacts":
  exec "rm -rf nimcache"
  exec "rm -f main"