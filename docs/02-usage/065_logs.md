# Logs

It can be vital to understand what is happening in Serena, especially when something goes wrong. 

You can access Serena's live logs via 
  * the [Serena dashboard](060_dashboard) (tab "Logs")
  * the [GUI tool](060_dashboard).

Additionally, logs are persisted in the Serena home directory, which, by default, is located at
  * `%USERPROFILE%\.serena\logs` on Windows
  * `~/.serena/logs` on Linux and macOS.

You can adjust the log level via the [global configuration](global-config).
You additionally have the option of enabling full tracing of language server communication (mostly for development purposes).
