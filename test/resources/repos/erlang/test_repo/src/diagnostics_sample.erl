-module(diagnostics_sample).
-export([broken_factory/0, broken_consumer/0]).

broken_factory() -> MissingGreeting.
broken_consumer() -> MissingConsumerValue.
