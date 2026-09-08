# SPDX-License-Identifier: GPL-3.0-or-later
"""
Client sessions (conversations) and their state.
"""

import logging
import secrets
from collections import OrderedDict

log = logging.getLogger(__name__)


class SerenaSession:
    """
    A client session, i.e. a conversation between an LLM and Serena, and the state pertaining to it.

    Session identity is supplied by the LLM: the session id is issued as part of Serena's instructions
    (system prompt/initial instructions) and passed by the LLM to tools which require it.
    """

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.described_type_names: set[str] = set()
        """the names of the REPL's result types whose documentation has already been provided in this session"""


class SessionRegistry:
    """
    Holds the sessions of an agent, creating them on demand and evicting the least recently used ones
    if their number exceeds the limit (session ids being supplied by LLMs, the set of ids is not controlled).
    """

    def __init__(self, max_sessions: int = 100) -> None:
        """
        :param max_sessions: the maximum number of sessions to keep
        """
        self._max_sessions = max_sessions
        self._sessions: OrderedDict[str, SerenaSession] = OrderedDict()

    def create_session(self) -> SerenaSession:
        """
        :return: a new session with a random id
        """
        return self.get_session(secrets.token_hex(4))

    def get_session(self, session_id: str) -> SerenaSession:
        """
        :param session_id: the session id
        :return: the session, which is created if it is unknown (an unknown id may e.g. stem from a session that has been
            evicted or from an earlier run of the server)
        """
        session = self._sessions.get(session_id)
        if session is None:
            session = SerenaSession(session_id)
            self._sessions[session_id] = session
            log.info("Created session %s (%d sessions)", session_id, len(self._sessions))
            while len(self._sessions) > self._max_sessions:
                evicted_id, _ = self._sessions.popitem(last=False)
                log.info("Evicted session %s", evicted_id)
        else:
            self._sessions.move_to_end(session_id)
        return session
