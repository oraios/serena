--  Intentionally invalid Ada — exercises the LSP diagnostics path.
--  The procedure body is missing the trailing `end Diagnostics_Sample;` token,
--  which libadalang flags as a syntax error regardless of project setup.
procedure Diagnostics_Sample is
begin
   null
