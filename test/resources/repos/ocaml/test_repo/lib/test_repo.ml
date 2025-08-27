module DemoModule = struct
  type value = string

  let someFunction s =
    s ^ " More String"
end

let rec fib n =
  if n < 2 then 1
  else fib (n-1) + fib (n-2)

let num_domains = 2

(* Functions that use Reason_utils module *)
let create_sample_user () =
  Reason_utils.make_user "Alice" 25

let greet_sample_user () = 
  let user = create_sample_user () in
  Reason_utils.greet_user user

let double_number x = Reason_utils.double x

let factorial n = Reason_utils.calculate_factorial n