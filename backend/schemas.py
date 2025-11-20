from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime

# Collections: product, order, user, codekey, contact

class Product(BaseModel):
    title: str
    game: str = Field(..., description="e.g., Fortnite, Roblox, Minecraft, CS2")
    reward_type: str = Field(..., description="e.g., skin, coins, item, bonus")
    description: str
    images: List[str] = []
    price_cents: int = Field(..., ge=0, description="Price in cents")
    currency: str = "usd"
    active: bool = True
    tags: List[str] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class ProductUpdate(BaseModel):
    title: Optional[str]
    game: Optional[str]
    reward_type: Optional[str]
    description: Optional[str]
    images: Optional[List[str]]
    price_cents: Optional[int]
    currency: Optional[str]
    active: Optional[bool]
    tags: Optional[List[str]]

class CodeKey(BaseModel):
    product_id: str
    code: str
    assigned: bool = False
    order_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class CartItem(BaseModel):
    product_id: str
    quantity: int = Field(..., ge=1, le=10)

class OrderCreate(BaseModel):
    items: List[CartItem]
    email: EmailStr
    name: Optional[str] = None

class Order(BaseModel):
    user_id: Optional[str] = None
    email: EmailStr
    name: Optional[str] = None
    items: List[CartItem]
    subtotal_cents: int
    total_cents: int
    currency: str = "usd"
    payment_intent_id: Optional[str] = None
    status: str = "pending"  # pending, paid, failed, refunded, fulfilled
    delivered_codes: List[str] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class User(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    password_hash: str
    role: str = "user"  # user, admin
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class ContactMessage(BaseModel):
    email: EmailStr
    subject: str
    message: str

class AdminAddCodes(BaseModel):
    product_id: str
    codes: List[str]
