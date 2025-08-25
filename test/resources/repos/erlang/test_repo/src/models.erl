%% Models module with record operations and business logic
-module(models).
-include("../include/records.hrl").
-include("../include/types.hrl").

%% Export functions
-export([
    create_user/4,
    update_user/2,
    get_user_by_id/1,
    create_order/3,
    add_item_to_order/3,
    calculate_order_total/1,
    validate_email/1,
    format_user_info/1
]).

%% User operations
-spec create_user(integer(), string(), email(), integer()) -> #user{}.
create_user(Id, Name, Email, Age) ->
    #user{
        id = Id,
        name = Name,
        email = Email,
        age = Age,
        active = true
    }.

-spec update_user(#user{}, [{atom(), term()}]) -> #user{}.
update_user(User, Updates) ->
    lists:foldl(fun update_user_field/2, User, Updates).

-spec get_user_by_id(user_id()) -> {ok, #user{}} | {error, not_found}.
get_user_by_id(Id) ->
    %% Simulate database lookup
    case Id of
        1 -> {ok, create_user(1, "John Doe", "john@example.com", 30)};
        2 -> {ok, create_user(2, "Jane Smith", "jane@example.com", 25)};
        _ -> {error, not_found}
    end.

%% Order operations
-spec create_order(integer(), user_id(), list()) -> #order{}.
create_order(Id, UserId, Items) ->
    #order{
        id = Id,
        user_id = UserId,
        items = Items,
        total = 0.0,
        status = pending
    }.

-spec add_item_to_order(#order{}, #item{}, quantity()) -> #order{}.
add_item_to_order(Order, Item, Quantity) ->
    NewItem = Item#item{id = Quantity}, % Store quantity in id field for simplicity
    Order#order{items = [NewItem | Order#order.items]}.

-spec calculate_order_total(#order{}) -> float().
calculate_order_total(#order{items = Items}) ->
    lists:foldl(fun(#item{price = Price, id = Qty}, Acc) -> 
        Acc + (Price * Qty) 
    end, 0.0, Items).

%% Helper functions
-spec update_user_field({atom(), term()}, #user{}) -> #user{}.
update_user_field({name, Name}, User) -> User#user{name = Name};
update_user_field({email, Email}, User) -> User#user{email = Email};
update_user_field({age, Age}, User) -> User#user{age = Age};
update_user_field({active, Active}, User) -> User#user{active = Active};
update_user_field(_, User) -> User.

-spec validate_email(string()) -> boolean().
validate_email(Email) ->
    string:str(Email, "@") > 0 andalso string:str(Email, ".") > 0.

-spec format_user_info(#user{}) -> string().
format_user_info(#user{name = Name, email = Email, age = Age, active = Active}) ->
    Status = case Active of
        true -> "active";
        false -> "inactive"
    end,
    lists:flatten(io_lib:format("~s (~s) - Age: ~w - Status: ~s", 
        [Name, Email, Age, Status])).