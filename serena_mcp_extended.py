#!/usr/bin/env python
"""
Entry point for the Serena server with context and mode support.
"""
import sys
from src.serena.mcp_extended import start_mcp_server

if __name__ == "__main__":
    start_mcp_server()