module DemoModule {
  type value = string;

  let someFunction s =
    s ++ " More String"
}

let num_domains = 2
let n = 20

let rec fib n =
  if n < 2 then 1
  else fib (n-1) + fib (n-2)

let () =
  let res = fib_par n num_domains in
  Printf.printf "fib(%d) = %d\n" n res
