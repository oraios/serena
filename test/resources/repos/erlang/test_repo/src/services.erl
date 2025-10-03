%% Services module implementing gen_server behavior
-module(services).
-behaviour(gen_server).
-include("../include/records.hrl").
-include("../include/types.hrl").

%% API exports
-export([
    start_link/0,
    stop/0,
    register_user/4,
    get_user/1,
    create_order/2,
    update_order_status/2,
    get_statistics/0
]).

%% gen_server callbacks
-export([
    init/1,
    handle_call/3,
    handle_cast/2,
    handle_info/2,
    terminate/2,
    code_change/3
]).

%% State record
-record(state, {
    users = #{} :: map(),
    orders = #{} :: map(),
    next_user_id = 1 :: integer(),
    next_order_id = 1 :: integer()
}).

%%%===================================================================
%%% API
%%%===================================================================

-spec start_link() -> {ok, pid()} | ignore | {error, term()}.
start_link() ->
    gen_server:start_link({local, ?MODULE}, ?MODULE, [], []).

-spec stop() -> ok.
stop() ->
    gen_server:stop(?MODULE).

-spec register_user(string(), email(), integer(), boolean()) -> {ok, user_id()} | {error, term()}.
register_user(Name, Email, Age, Active) ->
    gen_server:call(?MODULE, {register_user, Name, Email, Age, Active}).

-spec get_user(user_id()) -> {ok, #user{}} | {error, not_found}.
get_user(UserId) ->
    gen_server:call(?MODULE, {get_user, UserId}).

-spec create_order(user_id(), list()) -> {ok, integer()} | {error, term()}.
create_order(UserId, Items) ->
    gen_server:call(?MODULE, {create_order, UserId, Items}).

-spec update_order_status(integer(), atom()) -> ok | {error, term()}.
update_order_status(OrderId, Status) ->
    gen_server:call(?MODULE, {update_order_status, OrderId, Status}).

-spec get_statistics() -> #{atom() => integer()}.
get_statistics() ->
    gen_server:call(?MODULE, get_statistics).

%%%===================================================================
%%% gen_server callbacks
%%%===================================================================

-spec init([]) -> {ok, #state{}}.
init([]) ->
    {ok, #state{}}.

-spec handle_call(term(), {pid(), term()}, #state{}) -> handle_call_result().
handle_call({register_user, Name, Email, Age, Active}, _From, State) ->
    UserId = State#state.next_user_id,
    User = models:create_user(UserId, Name, Email, Age),
    UpdatedUser = models:update_user(User, [{active, Active}]),
    NewUsers = maps:put(UserId, UpdatedUser, State#state.users),
    NewState = State#state{
        users = NewUsers,
        next_user_id = UserId + 1
    },
    {reply, {ok, UserId}, NewState};

handle_call({get_user, UserId}, _From, State) ->
    case maps:get(UserId, State#state.users, not_found) of
        not_found -> {reply, {error, not_found}, State};
        User -> {reply, {ok, User}, State}
    end;

handle_call({create_order, UserId, Items}, _From, State) ->
    case maps:get(UserId, State#state.users, not_found) of
        not_found ->
            {reply, {error, user_not_found}, State};
        _User ->
            OrderId = State#state.next_order_id,
            Order = models:create_order(OrderId, UserId, Items),
            NewOrders = maps:put(OrderId, Order, State#state.orders),
            NewState = State#state{
                orders = NewOrders,
                next_order_id = OrderId + 1
            },
            {reply, {ok, OrderId}, NewState}
    end;

handle_call({update_order_status, OrderId, Status}, _From, State) ->
    case maps:get(OrderId, State#state.orders, not_found) of
        not_found ->
            {reply, {error, order_not_found}, State};
        Order ->
            UpdatedOrder = Order#order{status = Status},
            NewOrders = maps:put(OrderId, UpdatedOrder, State#state.orders),
            NewState = State#state{orders = NewOrders},
            {reply, ok, NewState}
    end;

handle_call(get_statistics, _From, State) ->
    Stats = #{
        total_users => maps:size(State#state.users),
        total_orders => maps:size(State#state.orders),
        next_user_id => State#state.next_user_id,
        next_order_id => State#state.next_order_id
    },
    {reply, Stats, State};

handle_call(_Request, _From, State) ->
    {reply, {error, unknown_request}, State}.

-spec handle_cast(term(), #state{}) -> {noreply, #state{}}.
handle_cast(_Msg, State) ->
    {noreply, State}.

-spec handle_info(term(), #state{}) -> {noreply, #state{}}.
handle_info(_Info, State) ->
    {noreply, State}.

-spec terminate(term(), #state{}) -> ok.
terminate(_Reason, _State) ->
    ok.

-spec code_change(term() | {down, term()}, #state{}, term()) -> {ok, #state{}}.
code_change(_OldVsn, State, _Extra) ->
    {ok, State}.