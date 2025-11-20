"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

# --------------------------------------------------
# Core app schemas for the MMORPG helper
# --------------------------------------------------

class FavoriteProfile(BaseModel):
    """
    Saved profiles the user bookmarks for quick access
    Collection name: "favoriteprofile"
    """
    game: str = Field(..., description="Game identifier, e.g., 'ffxiv' or 'osrs'")
    label: str = Field(..., description="Human-friendly label for this favorite")
    identifier: str = Field(..., description="Lookup key (e.g., character ID, username)")
    payload: Dict[str, Any] = Field(..., description="Raw stats payload returned by the API for quick rendering")

class SearchLog(BaseModel):
    """
    Track recent searches
    Collection name: "searchlog"
    """
    game: str = Field(..., description="Game identifier")
    query: Dict[str, Any] = Field(..., description="Parameters used for the search")
    result_ok: bool = Field(True, description="Whether the search succeeded")
    note: Optional[str] = Field(None, description="Optional diagnostic message")

# Example schemas (kept for reference):

class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")
