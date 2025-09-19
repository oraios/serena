# Utility functions library
{ lib }:

rec {
  # Math utilities
  math = {
    # Calculate factorial
    factorial = n:
      if n == 0
      then 1
      else n * factorial (n - 1);
    
    # Calculate fibonacci number
    fibonacci = n:
      if n <= 1
      then n
      else (fibonacci (n - 1)) + (fibonacci (n - 2));
    
    # Check if number is prime
    isPrime = n:
      let
        checkDivisible = i:
          if i * i > n then true
          else if lib.mod n i == 0 then false
          else checkDivisible (i + 1);
      in
        if n <= 1 then false
        else if n <= 3 then true
        else checkDivisible 2;
    
    # Greatest common divisor
    gcd = a: b:
      if b == 0
      then a
      else gcd b (lib.mod a b);
  };
  
  # String manipulation
  strings = {
    # Reverse a string
    reverse = str:
      let
        len = lib.stringLength str;
        chars = lib.genList (i: lib.substring (len - i - 1) 1 str) len;
      in
        lib.concatStrings chars;
    
    # Check if string is palindrome
    isPalindrome = str:
      str == strings.reverse str;
    
    # Convert to camelCase
    toCamelCase = str:
      let
        words = lib.splitString "-" str;
        capitalize = w: 
          if w == "" then ""
          else (lib.toUpper (lib.substring 0 1 w)) + (lib.substring 1 (-1) w);
        capitalizedWords = lib.tail (map capitalize words);
      in
        (lib.head words) + (lib.concatStrings capitalizedWords);
    
    # Convert to snake_case
    toSnakeCase = str:
      lib.replaceStrings ["-"] ["_"] (lib.toLower str);
  };
  
  # List operations
  lists = {
    # Get unique elements
    unique = list:
      lib.foldl' (acc: x:
        if lib.elem x acc
        then acc
        else acc ++ [x]
      ) [] list;
    
    # Zip two lists
    zip = list1: list2:
      let
        len1 = lib.length list1;
        len2 = lib.length list2;
        minLen = if len1 < len2 then len1 else len2;
      in
        lib.genList (i: {
          fst = lib.elemAt list1 i;
          snd = lib.elemAt list2 i;
        }) minLen;
    
    # Flatten nested list
    flatten = list:
      lib.foldl' (acc: x:
        if builtins.isList x
        then acc ++ (flatten x)
        else acc ++ [x]
      ) [] list;
    
    # Partition list by predicate
    partition = pred: list:
      lib.foldl' (acc: x:
        if pred x
        then { yes = acc.yes ++ [x]; no = acc.no; }
        else { yes = acc.yes; no = acc.no ++ [x]; }
      ) { yes = []; no = []; } list;
  };
  
  # Attribute set operations
  attrs = {
    # Deep merge two attribute sets
    deepMerge = attr1: attr2:
      lib.recursiveUpdate attr1 attr2;
    
    # Filter attributes by predicate
    filterAttrs = pred: attrs:
      lib.filterAttrs pred attrs;
    
    # Map over attribute values
    mapValues = f: attrs:
      lib.mapAttrs (name: value: f value) attrs;
    
    # Get nested attribute safely
    getAttrPath = path: default: attrs:
      lib.attrByPath path default attrs;
  };
  
  # File system utilities
  files = {
    # Read JSON file
    readJSON = path:
      builtins.fromJSON (builtins.readFile path);
    
    # Read TOML file
    readTOML = path:
      builtins.fromTOML (builtins.readFile path);
    
    # Check if path exists
    pathExists = path:
      builtins.pathExists path;
    
    # Get file type
    getFileType = path:
      let
        type = builtins.readFileType path;
      in
        if type == "directory" then "dir"
        else if type == "regular" then "file"
        else if type == "symlink" then "link"
        else "unknown";
  };
  
  # Validation utilities
  validate = {
    # Check if value is email
    isEmail = str:
      builtins.match "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$" str != null;
    
    # Check if value is URL
    isURL = str:
      builtins.match "^https?://[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}" str != null;
    
    # Check if value is valid version
    isVersion = str:
      builtins.match "^[0-9]+\\.[0-9]+\\.[0-9]+$" str != null;
  };
}