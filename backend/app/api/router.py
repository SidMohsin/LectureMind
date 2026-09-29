"""Aggregates all domain routers into a single API router.

Future phases add their own module here (auth.py, lectures.py, uploads.py,
processing.py, transcript.py, intelligence.py, search.py, chat.py,
history.py, profile.py) instead of growing a single flat file.
"""

from fastapi import APIRouter

from app.api import health

api_router = APIRouter()
api_router.include_router(health.router)
