"""PC-Agent — a local AI that controls a Windows PC.

Layers:
    brain       general chat + knowledge (Gemma 4 12B, 4-bit)
    dispatcher  natural language -> structured tool calls
    tools       the Executor: real Windows control (the "hands")
    safety      allowlists, confirmation gates, audit log
"""
__version__ = "0.1.0"
