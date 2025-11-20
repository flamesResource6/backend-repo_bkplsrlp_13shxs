import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import requests

from database import create_document, get_documents
from schemas import FavoriteProfile, SearchLog

app = FastAPI(title="MMORPG Helper API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "MMORPG Helper API is running"}

@app.get("/test")
def test_database():
    """Verify DB connectivity and list collections."""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        from database import db
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = getattr(db, 'name', None) or "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"

    return response

# --------------------------------------------------
# External game API helpers
# --------------------------------------------------

class OSRSSearch(BaseModel):
    username: str

class FFXIVSearch(BaseModel):
    name: str
    world: Optional[str] = None

# Fetch Old School RuneScape hiscores (official text API)
@app.post("/api/osrs/stats")
def get_osrs_stats(payload: OSRSSearch):
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username required")

    # Hiscore text format: 24 lines, comma-separated values per skill/boss
    # We'll hit the default hiscores (normal mode)
    url = f"https://secure.runescape.com/m=hiscore_oldschool/index_lite.ws?player={requests.utils.quote(username)}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 404:
            raise HTTPException(status_code=404, detail="Player not found")
        r.raise_for_status()
        lines = r.text.strip().split("\n")
        # Parse first 24 for skills
        skills = [
            "Overall","Attack","Defence","Strength","Hitpoints","Ranged","Prayer","Magic","Cooking","Woodcutting","Fletching","Fishing","Firemaking","Crafting","Smithing","Mining","Herblore","Agility","Thieving","Slayer","Farming","Runecraft","Hunter","Construction"
        ]
        parsed = {}
        for i, skill in enumerate(skills):
            try:
                rank, level, xp = lines[i].split(',')
                parsed[skill] = {"rank": int(rank), "level": int(level), "xp": int(xp)}
            except Exception:
                parsed[skill] = {"rank": -1, "level": 1, "xp": 0}

        # Log search
        try:
            create_document("searchlog", SearchLog(game="osrs", query={"username": username}, result_ok=True))
        except Exception:
            pass

        return {"game": "osrs", "username": username, "skills": parsed}
    except HTTPException:
        raise
    except Exception as e:
        try:
            create_document("searchlog", SearchLog(game="osrs", query={"username": username}, result_ok=False, note=str(e)[:200]))
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Failed to fetch OSRS stats")

# FFXIV Lodestone character search via XIVAPI (community API)
# We'll use a simple public search endpoint.
@app.post("/api/ffxiv/character")
def search_ffxiv_character(payload: FFXIVSearch):
    name = payload.name.strip()
    world = (payload.world or '').strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")

    params = {"name": name}
    if world:
        params["server"] = world

    try:
        r = requests.get("https://xivapi.com/character/search", params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        results = data.get("Results", [])

        # Log search
        try:
            create_document("searchlog", SearchLog(game="ffxiv", query=params, result_ok=True))
        except Exception:
            pass

        # Return a trimmed result set
        trimmed = [
            {
                "id": it.get("ID"),
                "name": it.get("Name"),
                "server": it.get("Server"),
                "avatar": it.get("Avatar"),
                "data_center": it.get("DC"),
            }
            for it in results
        ][:10]

        return {"game": "ffxiv", "results": trimmed}
    except Exception as e:
        try:
            create_document("searchlog", SearchLog(game="ffxiv", query=params, result_ok=False, note=str(e)[:200]))
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Failed to search FFXIV characters")

# Save favorite profiles
class FavoriteIn(BaseModel):
    game: str
    label: str
    identifier: str
    payload: Dict[str, Any]

@app.post("/api/favorites")
def add_favorite(fav: FavoriteIn):
    try:
        _id = create_document("favoriteprofile", FavoriteProfile(**fav.model_dump()))
        return {"ok": True, "id": _id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/favorites")
def list_favorites(limit: int = 50):
    try:
        docs = get_documents("favoriteprofile", {}, limit)
        # Convert ObjectId to str if present
        for d in docs:
            if "_id" in d:
                d["_id"] = str(d["_id"])
        return {"ok": True, "items": docs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
