%% Unit tests for utils module
-module(utils_tests).
-include_lib("eunit/include/eunit.hrl").

%%%===================================================================
%%% String utility tests
%%%===================================================================

capitalize_test() ->
    ?assertEqual("Hello", utils:capitalize("hello")),
    ?assertEqual("Test", utils:capitalize("test")),
    ?assertEqual("", utils:capitalize("")).

trim_test() ->
    ?assertEqual("hello", utils:trim("  hello  ")),
    ?assertEqual("test", utils:trim("test")),
    ?assertEqual("", utils:trim("   ")).

format_currency_test() ->
    ?assertEqual("$10.50", utils:format_currency(10.5)),
    ?assertEqual("$0.99", utils:format_currency(0.99)),
    ?assertEqual("$100.00", utils:format_currency(100.0)).

validate_input_test() ->
    ?assertEqual(true, utils:validate_input(email, "test@example.com")),
    ?assertEqual(false, utils:validate_input(email, "invalid")),
    ?assertEqual(true, utils:validate_input(age, 25)),
    ?assertEqual(false, utils:validate_input(age, -5)),
    ?assertEqual(true, utils:validate_input(name, "John")),
    ?assertEqual(false, utils:validate_input(name, "")).

%%%===================================================================
%%% List utility tests
%%%===================================================================

find_by_id_test() ->
    Items = [{item, 1, "first"}, {item, 2, "second"}, {item, 3, "third"}],
    ?assertEqual({ok, {item, 2, "second"}}, utils:find_by_id(2, Items)),
    ?assertEqual({error, not_found}, utils:find_by_id(999, Items)).

safe_nth_test() ->
    List = [a, b, c, d, e],
    ?assertEqual({ok, c}, utils:safe_nth(3, List)),
    ?assertEqual({error, out_of_bounds}, utils:safe_nth(10, List)),
    ?assertEqual({error, out_of_bounds}, utils:safe_nth(0, List)).

%%%===================================================================
%%% Math utility tests
%%%===================================================================

calculate_discount_test() ->
    ?assertEqual(90.0, utils:calculate_discount(100.0, 10.0)),
    ?assertEqual(75.0, utils:calculate_discount(100.0, 25.0)),
    ?assertEqual(100.0, utils:calculate_discount(100.0, 0.0)).

round_to_decimal_test() ->
    ?assertEqual(10.99, utils:round_to_decimal(10.9876, 2)),
    ?assertEqual(15.0, utils:round_to_decimal(15.0001, 2)),
    ?assertEqual(0.33, utils:round_to_decimal(1/3, 2)).

percentage_test() ->
    ?assertEqual(50.0, utils:percentage(50, 100)),
    ?assertEqual(25.0, utils:percentage(1, 4)),
    ?assertEqual(0.0, utils:percentage(10, 0)).

%%%===================================================================
%%% Date/Time utility tests
%%%===================================================================

timestamp_test() ->
    Timestamp = utils:timestamp(),
    ?assert(is_integer(Timestamp)),
    ?assert(Timestamp > 0).

format_datetime_test() ->
    % Test with a known timestamp
    Formatted = utils:format_datetime(1234567890),
    ?assert(is_list(Formatted)),
    ?assert(length(Formatted) > 0).

days_between_test() ->
    Day1 = 1000000,
    Day2 = 1000000 + (3 * 24 * 3600), % 3 days later
    ?assertEqual(3, utils:days_between(Day1, Day2)),
    ?assertEqual(3, utils:days_between(Day2, Day1)).