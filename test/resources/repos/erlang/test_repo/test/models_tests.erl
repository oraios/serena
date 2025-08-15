%% Unit tests for models module
-module(models_tests).
-include_lib("eunit/include/eunit.hrl").
-include("../include/records.hrl").

%%%===================================================================
%%% Test fixtures
%%%===================================================================

sample_user() ->
    models:create_user(1, "John Doe", "john@example.com", 30).

sample_order() ->
    Items = [
        #item{id = 1, name = "Widget", price = 10.99, category = "tools"},
        #item{id = 2, name = "Gadget", price = 25.50, category = "electronics"}
    ],
    models:create_order(1, 1, Items).

%%%===================================================================
%%% User tests
%%%===================================================================

create_user_test() ->
    User = models:create_user(1, "John Doe", "john@example.com", 30),
    ?assertEqual(1, User#user.id),
    ?assertEqual("John Doe", User#user.name),
    ?assertEqual("john@example.com", User#user.email),
    ?assertEqual(30, User#user.age),
    ?assertEqual(true, User#user.active).

update_user_test() ->
    User = sample_user(),
    UpdatedUser = models:update_user(User, [{name, "Jane Doe"}, {age, 25}]),
    ?assertEqual("Jane Doe", UpdatedUser#user.name),
    ?assertEqual(25, UpdatedUser#user.age),
    ?assertEqual("john@example.com", UpdatedUser#user.email). % unchanged

get_user_by_id_test() ->
    ?assertEqual({ok, #user{id = 1, name = "John Doe"}}, 
                 models:get_user_by_id(1)),
    ?assertEqual({error, not_found}, models:get_user_by_id(999)).

%%%===================================================================
%%% Order tests
%%%===================================================================

create_order_test() ->
    Order = models:create_order(1, 1, []),
    ?assertEqual(1, Order#order.id),
    ?assertEqual(1, Order#order.user_id),
    ?assertEqual([], Order#order.items),
    ?assertEqual(pending, Order#order.status).

calculate_order_total_test() ->
    Order = sample_order(),
    Total = models:calculate_order_total(Order),
    ?assertEqual(36.49, Total). % 10.99 * 1 + 25.50 * 2

%%%===================================================================
%%% Validation tests
%%%===================================================================

validate_email_test() ->
    ?assertEqual(true, models:validate_email("user@example.com")),
    ?assertEqual(true, models:validate_email("test.email@domain.co.uk")),
    ?assertEqual(false, models:validate_email("invalid-email")),
    ?assertEqual(false, models:validate_email("@domain.com")),
    ?assertEqual(false, models:validate_email("user@")).

format_user_info_test() ->
    User = sample_user(),
    Info = models:format_user_info(User),
    ?assert(string:str(Info, "John Doe") > 0),
    ?assert(string:str(Info, "john@example.com") > 0),
    ?assert(string:str(Info, "30") > 0),
    ?assert(string:str(Info, "active") > 0).