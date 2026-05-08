package Helper is

   type Greeting_Style is (Friendly, Formal);

   function Greet (Name : String) return String;

end Helper;
