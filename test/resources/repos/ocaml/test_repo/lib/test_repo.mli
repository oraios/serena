module DemoModule : sig
  type value = string
  val someFunction : string -> string
end

val fib : int -> int
val num_domains : int

(* Functions using Reason modules *)
val create_sample_user : unit -> Reason_utils.user
val greet_sample_user : unit -> string
val double_number : int -> int
val factorial : int -> int