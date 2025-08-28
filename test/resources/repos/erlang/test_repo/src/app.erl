%% Main application module
-module(app).
-behaviour(application).
-include("../include/records.hrl").

%% Application callbacks
-export([
    start/2,
    stop/1
]).

%% API exports
-export([
    start_services/0,
    stop_services/0,
    get_config/0,
    health_check/0
]).

%%%===================================================================
%%% Application callbacks
%%%===================================================================

-spec start(application:start_type(), term()) -> {ok, pid()} | {error, term()}.
start(_StartType, _StartArgs) ->
    io:format("Starting test application~n"),
    case start_services() of
        ok ->
            supervisor:start_link({local, app_sup}, ?MODULE, []);
        {error, Reason} ->
            {error, Reason}
    end.

-spec stop(term()) -> ok.
stop(_State) ->
    io:format("Stopping test application~n"),
    stop_services(),
    ok.

%%%===================================================================
%%% API functions
%%%===================================================================

-spec start_services() -> ok | {error, term()}.
start_services() ->
    try
        {ok, _Pid} = services:start_link(),
        io:format("Services started successfully~n"),
        ok
    catch
        error:Reason ->
            io:format("Failed to start services: ~p~n", [Reason]),
            {error, Reason}
    end.

-spec stop_services() -> ok.
stop_services() ->
    try
        services:stop(),
        io:format("Services stopped successfully~n"),
        ok
    catch
        error:Reason ->
            io:format("Error stopping services: ~p~n", [Reason]),
            ok
    end.

-spec get_config() -> #config{}.
get_config() ->
    #config{
        database_url = "postgresql://localhost:5432/testdb",
        port = 8080,
        debug = true
    }.

-spec health_check() -> {ok, #{atom() => term()}} | {error, term()}.
health_check() ->
    try
        Stats = services:get_statistics(),
        Config = get_config(),
        HealthInfo = #{
            status => healthy,
            timestamp => utils:timestamp(),
            config => Config,
            statistics => Stats,
            uptime => erlang:statistics(wall_clock)
        },
        {ok, HealthInfo}
    catch
        error:Reason ->
            {error, {health_check_failed, Reason}}
    end.

%%%===================================================================
%%% Supervisor callbacks (simple implementation)
%%%===================================================================

init([]) ->
    %% Simple supervisor strategy
    SupFlags = #{
        strategy => one_for_one,
        intensity => 5,
        period => 10
    },
    
    ChildSpecs = [
        #{
            id => services,
            start => {services, start_link, []},
            restart => permanent,
            shutdown => 5000,
            type => worker,
            modules => [services]
        }
    ],
    
    {ok, {SupFlags, ChildSpecs}}.