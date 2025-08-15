%% Utility functions module
-module(utils).
-include("../include/types.hrl").

%% String utilities
-export([
    capitalize/1,
    trim/1,
    split_string/2,
    format_currency/1,
    validate_input/2
]).

%% List utilities
-export([
    find_by_id/2,
    group_by/2,
    partition_by/2,
    safe_nth/2
]).

%% Math utilities
-export([
    calculate_discount/2,
    round_to_decimal/2,
    percentage/2
]).

%% Date/Time utilities
-export([
    timestamp/0,
    format_datetime/1,
    days_between/2
]).

%%%===================================================================
%%% String utilities
%%%===================================================================

-spec capitalize(string()) -> string().
capitalize([]) -> [];
capitalize([H|T]) -> [string:to_upper(H) | T].

-spec trim(string()) -> string().
trim(String) ->
    string:strip(string:strip(String, right), left).

-spec split_string(string(), string()) -> [string()].
split_string(String, Delimiter) ->
    string:tokens(String, Delimiter).

-spec format_currency(float()) -> string().
format_currency(Amount) ->
    lists:flatten(io_lib:format("$~.2f", [Amount])).

-spec validate_input(atom(), term()) -> boolean().
validate_input(email, Email) when is_list(Email) ->
    models:validate_email(Email);
validate_input(age, Age) when is_integer(Age) ->
    Age >= 0 andalso Age =< 150;
validate_input(name, Name) when is_list(Name) ->
    length(Name) > 0 andalso length(Name) =< 100;
validate_input(_, _) ->
    false.

%%%===================================================================
%%% List utilities
%%%===================================================================

-spec find_by_id(integer(), [tuple()]) -> {ok, tuple()} | {error, not_found}.
find_by_id(_Id, []) -> {error, not_found};
find_by_id(Id, [H|T]) when element(2, H) =:= Id -> {ok, H};
find_by_id(Id, [_|T]) -> find_by_id(Id, T).

-spec group_by(fun((term()) -> term()), [term()]) -> [{term(), [term()]}].
group_by(Fun, List) ->
    Dict = lists:foldl(fun(Item, Acc) ->
        Key = Fun(Item),
        case lists:keyfind(Key, 1, Acc) of
            {Key, Values} ->
                lists:keyreplace(Key, 1, Acc, {Key, [Item|Values]});
            false ->
                [{Key, [Item]}|Acc]
        end
    end, [], List),
    [{K, lists:reverse(V)} || {K, V} <- Dict].

-spec partition_by(fun((term()) -> boolean()), [term()]) -> {[term()], [term()]}.
partition_by(Predicate, List) ->
    lists:partition(Predicate, List).

-spec safe_nth(integer(), [term()]) -> {ok, term()} | {error, out_of_bounds}.
safe_nth(N, List) when N > 0 andalso N =< length(List) ->
    {ok, lists:nth(N, List)};
safe_nth(_, _) ->
    {error, out_of_bounds}.

%%%===================================================================
%%% Math utilities
%%%===================================================================

-spec calculate_discount(float(), float()) -> float().
calculate_discount(Price, DiscountPercent) when DiscountPercent >= 0 andalso DiscountPercent =< 100 ->
    Price * (100 - DiscountPercent) / 100.

-spec round_to_decimal(float(), integer()) -> float().
round_to_decimal(Number, Decimals) ->
    Factor = math:pow(10, Decimals),
    round(Number * Factor) / Factor.

-spec percentage(number(), number()) -> float().
percentage(Part, Total) when Total =/= 0 ->
    (Part / Total) * 100;
percentage(_, 0) ->
    0.0.

%%%===================================================================
%%% Date/Time utilities
%%%===================================================================

-spec timestamp() -> integer().
timestamp() ->
    {MegaSecs, Secs, _MicroSecs} = os:timestamp(),
    MegaSecs * 1000000 + Secs.

-spec format_datetime(integer()) -> string().
format_datetime(Timestamp) ->
    {{Year, Month, Day}, {Hour, Minute, Second}} = 
        calendar:gregorian_seconds_to_datetime(Timestamp + 62167219200),
    lists:flatten(io_lib:format("~4..0w-~2..0w-~2..0w ~2..0w:~2..0w:~2..0w", 
        [Year, Month, Day, Hour, Minute, Second])).

-spec days_between(integer(), integer()) -> integer().
days_between(Timestamp1, Timestamp2) ->
    abs(Timestamp2 - Timestamp1) div (24 * 3600).