open Test_repo

let test_fib () =
  assert (fib 0 = 1);
  assert (fib 1 = 1);
  assert (fib 2 = 2);
  assert (fib 5 = 8);
  Printf.printf "fib tests passed\n"

let test_demo_module () =
  let result = DemoModule.someFunction "Test" in
  assert (result = "Test More String");
  Printf.printf "DemoModule tests passed\n"

let () =
  test_fib ();
  test_demo_module ();
  Printf.printf "All tests passed!\n"