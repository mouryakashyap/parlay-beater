"""
Match routes — thin HTTP layer. Validates input, calls service, returns response.
No DB queries here. No business logic here.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import match_service
from app.schemas.match import MatchRead, MatchListResponse

router = APIRouter(prefix="/matches", tags=["matches"])


@router.get("/upcoming", response_model=MatchListResponse)
def get_upcoming_matches(
    league: str | None = Query(None, description="Filter by league code, e.g. PL, PD, SA"),
    days: int = Query(7, ge=1, le=30, description="How many days ahead to look"),
    db: Session = Depends(get_db),
):
    """
    Return scheduled matches in the next N days.
    Wrapped in MatchListResponse so the client gets a total count alongside items.
    """
    matches = match_service.get_upcoming_matches(db, league=league, days=days)
    return MatchListResponse(total=len(matches), items=matches)


@router.get("/finished", response_model=MatchListResponse)
def get_finished_matches(
    days_back: int = Query(7, ge=1, le=30, description="How many days back to look"),
    db: Session = Depends(get_db),
):
    """Return recently finished matches, newest first."""
    matches = match_service.get_finished_matches(db, days_back=days_back)
    return MatchListResponse(total=len(matches), items=matches)


@router.get("/{match_id}", response_model=MatchRead)
def get_match(match_id: int, db: Session = Depends(get_db)):
    """Return a single match by its internal DB id. 404 if not found."""
    match = match_service.get_match(db, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    return match
