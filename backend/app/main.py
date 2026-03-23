from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import SessionLocal, init_db
from .models import User
from .routers.advisor_ai import router as advisor_ai_router
from .routers.contact_draft import router as contact_draft_router
from .routers.discovery import router as discovery_router
from .routers.health import router as health_router
from .routers.mentors import router as mentors_router
from .routers.settings import router as settings_router
from .routers.timeline import router as timeline_router
from .services.job_runner import backfill_raw_mentors_for_legacy_jobs, recover_interrupted_jobs

app = FastAPI(title=settings.app_name)

# Dev-friendly CORS: allow frontend dev server to call backend API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(discovery_router)
app.include_router(mentors_router)
app.include_router(timeline_router)
app.include_router(settings_router)
app.include_router(advisor_ai_router)
app.include_router(contact_draft_router)


@app.on_event("startup")
def on_startup() -> None:
    settings.ensure_dirs()
    init_db()

    with SessionLocal() as db:
        recover_interrupted_jobs(db)
        backfill_raw_mentors_for_legacy_jobs(db)
        default_user = db.get(User, 1)
        if default_user is None:
            db.add(User(id=1, email=settings.default_user_email, display_name=settings.default_user_name))
            db.commit()


