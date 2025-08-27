open Test_repo

let n = 20

let () =
  let res = fib n in
  Printf.printf "fib(%d) = %d\n" n res;
  let greeting = DemoModule.someFunction "Hello" in
  Printf.printf "%s\n" greeting;
  
  (* Test Reason module integration *)
  let user_greeting = greet_sample_user () in
  Printf.printf "Reason says: %s\n" user_greeting;
  
  let doubled = double_number 21 in
  Printf.printf "Double of 21 = %d\n" doubled;
  
  let fact_5 = factorial 5 in
  Printf.printf "Factorial of 5 = %d\n" fact_5