defmodule DiagnosticsSample do
  def broken_factory do
    missing_greeting
  end

  def broken_consumer do
    value = broken_factory()
    {value, missing_consumer_value}
  end
end
