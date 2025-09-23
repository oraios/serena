# Utility functions module

import std/[strutils, math, algorithm]

proc formatNumber*(n: int): string =
  ## Formats a number with thousand separators
  let s = $n
  var result = ""
  var count = 0
  for i in countdown(s.high, 0):
    if count == 3:
      result = "," & result
      count = 0
    result = s[i] & result
    inc count
  return result

proc reverseString*(s: string): string =
  ## Reverses a string
  result = s
  result.reverse()

proc isPalindrome*(s: string): bool =
  ## Checks if a string is a palindrome
  let cleaned = s.toLowerAscii.multiReplace((" ", ""), (",", ""), (".", ""))
  return cleaned == cleaned.reversed.join("")

proc fibonacci*(n: int): seq[int] =
  ## Generates fibonacci sequence up to n terms
  if n <= 0: return @[]
  if n == 1: return @[0]
  if n == 2: return @[0, 1]

  result = @[0, 1]
  for i in 2..<n:
    result.add(result[^1] + result[^2])

proc factorial*(n: int): int =
  ## Calculates factorial of n
  if n <= 1: return 1
  result = 1
  for i in 2..n:
    result *= i

proc gcd*(a, b: int): int =
  ## Calculates greatest common divisor
  var (x, y) = (a, b)
  while y != 0:
    (x, y) = (y, x mod y)
  return x

proc lcm*(a, b: int): int =
  ## Calculates least common multiple
  return abs(a * b) div gcd(a, b)

template timeIt*(body: untyped): untyped =
  ## Template to time code execution
  let start = cpuTime()
  body
  let elapsed = cpuTime() - start
  echo "Execution time: ", elapsed, " seconds"

iterator countUp*(a, b: int, step: int = 1): int =
  ## Custom count up iterator
  var i = a
  while i <= b:
    yield i
    i += step

proc mapSeq*[T, U](s: seq[T], f: proc(x: T): U): seq[U] =
  ## Maps a function over a sequence
  result = newSeq[U](s.len)
  for i, item in s:
    result[i] = f(item)