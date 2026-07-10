"""Pin the polars engine affinity so every collect runs on the streaming engine.

Streaming keeps peak memory bounded on the big tables and falls back to the
in-memory engine per node for anything it cannot stream. Imported for its side
effect by the package init.
"""

import polars as pl

pl.Config.set_engine_affinity("streaming")
