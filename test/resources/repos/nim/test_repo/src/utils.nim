## Utility functions for string and sequence operations.

import std/strutils

proc trim*(s: string): string =
  ## Remove leading and trailing whitespace.
  result = s.strip()

proc split_words*(s: string): seq[string] =
  ## Split a string into words by whitespace.
  result = s.splitWhitespace()

proc starts_with*(s, prefix: string): bool =
  ## Check if s starts with the given prefix.
  result = s.startsWith(prefix)

proc ends_with*(s, suffix: string): bool =
  ## Check if s ends with the given suffix.
  result = s.endsWith(suffix)

proc repeat_string*(s: string, count: int): string =
  ## Repeat a string count times.
  result = s.repeat(count)

type
  Logger* = object
    ## A simple logger with a name and level.
    name*: string
    level*: int

proc newLogger*(name: string, level: int = 0): Logger =
  ## Create a new Logger instance.
  result = Logger(name: name, level: level)

proc log*(logger: Logger, message: string) =
  ## Log a message if level is sufficient.
  if logger.level >= 0:
    echo "[" & logger.name & "] " & message

proc debug*(logger: Logger, message: string) =
  ## Log a debug message.
  if logger.level <= 0:
    echo "[DEBUG " & logger.name & "] " & message

proc info*(logger: Logger, message: string) =
  ## Log an info message.
  if logger.level <= 1:
    echo "[INFO " & logger.name & "] " & message
