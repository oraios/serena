# SPDX-License-Identifier: GPL-3.0-or-later

from serena.config.context_mode import SerenaAgentContext, SerenaAgentMode

if __name__ == "__main__":
    print("---------- Available modes: ----------")
    for mode_name in SerenaAgentMode.list_registered_mode_names():
        mode = SerenaAgentMode.load(mode_name)
        mode.print_overview()
        print("\n")
    print("---------- Available contexts: ----------")
    for context_name in SerenaAgentContext.list_registered_context_names():
        context = SerenaAgentContext.load(context_name)
        context.print_overview()
        print("\n")
