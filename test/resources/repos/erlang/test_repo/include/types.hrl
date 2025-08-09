%% Type definitions for the test repository
-ifndef(TYPES_HRL).
-define(TYPES_HRL, true).

%% Custom types
-type user_id() :: pos_integer().
-type email() :: string().
-type status() :: active | inactive | suspended.
-type price() :: float().
-type quantity() :: non_neg_integer().

%% Complex types
-type order_line() :: {item_id :: pos_integer(), quantity :: quantity(), price :: price()}.
-type search_result() :: {ok, list()} | {error, term()}.

%% Callback types for behaviors
-type init_result() :: {ok, term()} | {stop, term()}.
-type handle_call_result() :: {reply, term(), term()} | {stop, term(), term()}.

-endif.