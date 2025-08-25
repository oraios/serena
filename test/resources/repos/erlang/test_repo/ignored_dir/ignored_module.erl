%% This module should be ignored by tests
-module(ignored_module).

%% This is in the ignored directory and should not be processed
-export([ignored_function/0]).

ignored_function() ->
    "This should not appear in symbol searches".