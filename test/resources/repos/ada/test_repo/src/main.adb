with Ada.Text_IO;
with Helper;

procedure Main is
   Greeting : constant String := Helper.Greet ("Ada");
begin
   Ada.Text_IO.Put_Line (Greeting);
end Main;
