(* OCaml module for utility functions - originally written in Reason syntax *)

type user = {
  name : string;
  age : int;
}

let make_user name age = {name; age}

let greet_user user =
  "Hello, " ^ user.name ^ "! You are " ^ (string_of_int user.age) ^ " years old."

let double x = x * 2

let calculate_factorial n =
  let rec fact acc num =
    if num <= 1 then acc
    else fact (acc * num) (num - 1)
  in
  fact 1 n