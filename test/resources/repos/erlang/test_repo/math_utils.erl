-module(math_utils).
-export([add/2, multiply/2, factorial/1]).

%% Add two numbers
add(X, Y) ->
    X + Y.

%% Multiply two numbers
multiply(X, Y) ->
    X * Y.

%% Calculate factorial
factorial(0) ->
    1;
factorial(N) when N > 0 ->
    N * factorial(N - 1).