module DemoModule = struct
  type value = string

  let someFunction s =
    s ^ " More String"
end

let rec fib n =
  if n < 2 then 1
  else fib (n-1) + fib (n-2)

let num_domains = 2