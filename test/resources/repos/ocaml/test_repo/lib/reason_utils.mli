(* Interface file for reason_utils module *)

type user = {
  name : string;
  age : int;
}

val make_user : string -> int -> user
val greet_user : user -> string
val double : int -> int
val calculate_factorial : int -> int