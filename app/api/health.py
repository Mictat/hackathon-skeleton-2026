from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.db import get_db

router = APIRouter()


@router.get("/api/health")
def health(db=Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "db": "up", "app": "TEMPNAME", "version": "0.1.0"}
