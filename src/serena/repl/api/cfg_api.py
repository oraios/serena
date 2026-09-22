# SPDX-License-Identifier: GPL-3.0-or-later
"""
The implementation of operations concerning Serena's configuration and session state.
"""

from typing import TYPE_CHECKING

from serena.tools import GetCurrentConfigTool, OpenDashboardTool

from ..facade import FacadeApi, facade_method

if TYPE_CHECKING:
    from serena.agent import SerenaAgent


class ConfigApi(FacadeApi):
    def __init__(self, agent: "SerenaAgent") -> None:
        super().__init__(agent, name="cfg", description="Serena's configuration and session state (incl. the dashboard)")

    @facade_method(corresponding_tool=GetCurrentConfigTool)
    def get_current_config(self) -> str:
        """
        Provides the current configuration of the agent, including the active and available projects, tools, contexts, and modes.

        :return: the configuration overview
        """
        return self._agent.get_current_config_overview()

    @facade_method(corresponding_tool=OpenDashboardTool)
    def open_dashboard(self) -> str:
        """
        Opens the Serena web dashboard in the default web browser.
        The dashboard provides logs, session information, and tool usage statistics.

        :return: a message indicating whether the dashboard could be opened
        """
        if self._agent.open_dashboard():
            return f"Serena web dashboard has been opened in the user's default web browser: {self._agent.get_dashboard_url()}"
        else:
            return f"Serena web dashboard could not be opened automatically; tell the user to open it via {self._agent.get_dashboard_url()}"
