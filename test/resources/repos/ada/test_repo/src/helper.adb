package body Helper is

   function Greet (Name : String) return String is
      Prefix : constant String := "Hello, ";
   begin
      return Prefix & Name & "!";
   end Greet;

end Helper;
