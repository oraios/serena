-module(hello).
-export([hello_world/0, greet/1, calculate_sum/2]).

%% Simple hello world function
hello_world() ->
    io:format("Hello, World!~n").

%% Greet a person by name
greet(Name) ->
    io:format("Hello, ~s!~n", [Name]).

%% Calculate sum of two numbers
calculate_sum(A, B) ->
    A + B.