# Bindings whose name is not plain text at the start of the symbol's range, next to ones that are.
# Each binding owns its trailing semicolon; the expressions inside it and inherited names do not.
{
  plain = 1;
  "quoted-name" = 2;
  split
    = 3;
  commented /* before the equals sign */ = 4;
  services.web.hosts."web-host" = { root = "/srv"; };
  lambda = x: x;
  formals = { a }: { b = a; };
  compare = y: y == 1;
  ${"dynamic"} = 5;
  lineComment # before the equals sign
    = 6;
  blockComment /* over
    two lines */ = 7;
  inherit (builtins) toString;
}
