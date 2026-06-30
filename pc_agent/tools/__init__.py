"""Importing this package registers every tool into registry.REGISTRY."""
from . import system_info   # noqa: F401
from . import settings      # noqa: F401
from . import apps          # noqa: F401
from . import tasks         # noqa: F401
from . import input_control  # noqa: F401
from . import audio         # noqa: F401
from . import display       # noqa: F401
from . import network       # noqa: F401
from . import screen        # noqa: F401
from .registry import REGISTRY, all_schemas, get  # noqa: F401

__all__ = ["REGISTRY", "all_schemas", "get"]
