"""Decode Deadlock match metadata and query it with polars.

Importing the package pins the polars engine affinity to the streaming engine,
see engine.py.
"""

from deadlock_matches import engine as engine
