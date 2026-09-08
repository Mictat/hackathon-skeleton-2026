import app.models  # noqa: F401 — registers all tables on Base
from app.db import Base, engine

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
print("✔ database reset — 12 tables created")
