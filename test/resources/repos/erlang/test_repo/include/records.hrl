%% Common record definitions for the test repository
-ifndef(RECORDS_HRL).
-define(RECORDS_HRL, true).

%% User record definition
-record(user, {
    id :: integer(),
    name :: string(),
    email :: string(),
    age :: integer(),
    active = true :: boolean()
}).

%% Order record definition
-record(order, {
    id :: integer(),
    user_id :: integer(),
    items = [] :: list(),
    total :: float(),
    status = pending :: pending | processing | completed | cancelled
}).

%% Item record definition
-record(item, {
    id :: integer(),
    name :: string(),
    price :: float(),
    category :: string()
}).

%% Configuration record
-record(config, {
    database_url :: string(),
    port :: integer(),
    debug = false :: boolean()
}).

-endif.