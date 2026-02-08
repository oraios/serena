open Test_repo

let n = 20

let () =
  let res = fib n in
  Printf.printf "fib(%d) = %d\n" n res;
  let greeting = DemoModule.someFunction "Hello" in
  Printf.printf "%s\n" greeting