"""Aggregates all domain routers into a single API router.

Future phases add their own module here (auth.py, lectures.py, uploads.py,
processing.py, transcript.py, intelligence.py, search.py, chat.py,
history.py, profile.py) instead of growing a single flat file.
"""

from fastapi import APIRouter

from app.api import health, ingestion, lectures, me, workspace

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(me.router)
# Registered before the lectures router so /lectures/uploads and /lectures/sources
# aren't shadowed by /lectures/{lecture_id}.
api_router.include_router(ingestion.router)
api_router.include_router(lectures.router)
api_router.include_router(workspace.router)
