from .discovery import router as discovery_router
from .health import router as health_router
from .mentors import router as mentors_router
from .timeline import router as timeline_router

__all__ = [
    "discovery_router",
    "health_router",
    "mentors_router",
    "timeline_router",
]
