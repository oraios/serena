# Bindings after an astral character, which takes two UTF-16 code units: a body written back as shown must
# leave the file unchanged, the newline, the next binding and the closing brace included.
{
  astral = "🚀";
  next = 1;
  inline = { x = "🚀"; y = 2; };
  last = { z = "🚀";};
}
