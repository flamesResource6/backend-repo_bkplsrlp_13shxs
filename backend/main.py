import os
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from jose import JWTError, jwt
from passlib.context import CryptContext
import requests

from database import db, create_document, get_documents
from schemas import (
    Product, ProductUpdate, CodeKey,
    OrderCreate, Order, CartItem,
    UserRegister, UserLogin, User, TokenResponse,
    ContactMessage, AdminAddCodes,
)

# ENV
PORT = int(os.getenv("PORT", 8000))
JWT_SECRET = os.getenv("JWT_SECRET", "devsecret")
JWT_ALG = "HS256"
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY", "")
SITE_NAME = os.getenv("SITE_NAME", "BlueCodes")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="Game Codes Store API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JWT helpers
class TokenData(BaseModel):
    email: Optional[str] = None
    role: str = "user"

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=12))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALG)
    return encoded_jwt

async def get_user_by_email(email: str) -> Optional[dict]:
    res = await get_documents("user", {"email": email}, limit=1)
    return res[0] if res else None

async def get_current_user(token: str = Depends(lambda authorization: authorization)):
    # In this environment, simple header pass through via query for brevity
    # Expect token string (access_token)
    credentials_exception = HTTPException(status_code=401, detail="Could not validate credentials")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        email: str = payload.get("sub")
        role: str = payload.get("role", "user")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = await get_user_by_email(email)
    if user is None:
        raise credentials_exception
    return {"email": email, "role": role, "_id": str(user.get("_id"))}

# Health
@app.get("/")
async def root():
    return {"ok": True, "service": "Game Codes Store API", "site": SITE_NAME}

@app.get("/test")
async def test():
    # simple db ping
    try:
        _ = await get_documents("product", {}, limit=1)
        db_ok = True
    except Exception:
        db_ok = False
    return {"ok": True, "db": db_ok}

# Auth
@app.post("/api/auth/register", response_model=TokenResponse)
async def register(payload: UserRegister):
    existing = await get_user_by_email(payload.email)
    if existing:
        raise HTTPException(400, "Email already registered")
    password_hash = pwd_context.hash(payload.password)
    doc = payload.dict()
    doc.pop("password")
    user = User(**{**doc, "password_hash": password_hash, "role": "user", "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()})
    inserted = await create_document("user", user.dict())
    token = create_access_token({"sub": payload.email, "role": "user"})
    return TokenResponse(access_token=token)

@app.post("/api/auth/login", response_model=TokenResponse)
async def login(payload: UserLogin):
    user = await get_user_by_email(payload.email)
    if not user:
        raise HTTPException(400, "Invalid credentials")
    if not pwd_context.verify(payload.password, user.get("password_hash")):
        raise HTTPException(400, "Invalid credentials")
    token = create_access_token({"sub": payload.email, "role": user.get("role", "user")})
    return TokenResponse(access_token=token)

# Products
@app.post("/api/admin/products", response_model=dict)
async def create_product(product: Product, current=Depends(get_current_user)):
    if current["role"] != "admin":
        raise HTTPException(403, "Admin only")
    now = datetime.utcnow()
    prod = {**product.dict(), "created_at": now, "updated_at": now}
    res = await create_document("product", prod)
    return {"id": str(res)}

@app.get("/api/products", response_model=List[dict])
async def list_products(game: Optional[str] = None, reward_type: Optional[str] = None, min_price: Optional[int] = None, max_price: Optional[int] = None):
    q: dict = {"active": True}
    if game:
        q["game"] = game
    if reward_type:
        q["reward_type"] = reward_type
    if min_price is not None or max_price is not None:
        price_q = {}
        if min_price is not None:
            price_q["$gte"] = int(min_price)
        if max_price is not None:
            price_q["$lte"] = int(max_price)
        q["price_cents"] = price_q
    docs = await get_documents("product", q, limit=100)
    # Ensure id string
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs

@app.get("/api/products/{product_id}", response_model=dict)
async def get_product(product_id: str):
    docs = await get_documents("product", {"_id": {"$oid": product_id}}, limit=1)
    if not docs:
        raise HTTPException(404, "Product not found")
    d = docs[0]
    d["id"] = str(d.pop("_id"))
    return d

@app.patch("/api/admin/products/{product_id}")
async def update_product(product_id: str, payload: ProductUpdate, current=Depends(get_current_user)):
    if current["role"] != "admin":
        raise HTTPException(403, "Admin only")
    # Using simple update via create_document helper is not available; stub for demo
    raise HTTPException(501, "Update not implemented in this environment")

# Codes management
@app.post("/api/admin/codes", response_model=dict)
async def add_codes(payload: AdminAddCodes, current=Depends(get_current_user)):
    if current["role"] != "admin":
        raise HTTPException(403, "Admin only")
    now = datetime.utcnow()
    inserted = []
    for code in payload.codes:
        ck = CodeKey(product_id=payload.product_id, code=code, assigned=False, order_id=None, created_at=now, updated_at=now)
        res = await create_document("codekey", ck.dict())
        inserted.append(str(res))
    return {"inserted": inserted}

# Checkout simulation with Stripe intent creation optional
class CheckoutInitResponse(BaseModel):
    client_secret: Optional[str]
    order_id: str
    total_cents: int

from bson import ObjectId  # type: ignore

async def find_available_codes(product_id: str, quantity: int) -> List[dict]:
    docs = await get_documents("codekey", {"product_id": product_id, "assigned": False}, limit=quantity)
    return docs

@app.post("/api/checkout/init", response_model=CheckoutInitResponse)
async def checkout_init(payload: OrderCreate):
    # Calculate subtotal
    subtotal = 0
    currency = "usd"
    product_cache = {}
    for item in payload.items:
        prods = await get_documents("product", {"_id": {"$oid": item.product_id}}, limit=1)
        if not prods:
            raise HTTPException(400, f"Invalid product {item.product_id}")
        p = prods[0]
        product_cache[item.product_id] = p
        subtotal += int(p["price_cents"]) * int(item.quantity)
        currency = p.get("currency", "usd")
    total = subtotal

    order = Order(
        user_id=None,
        email=payload.email,
        name=payload.name,
        items=payload.items,
        subtotal_cents=subtotal,
        total_cents=total,
        currency=currency,
        status="pending",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    order_id = await create_document("order", order.dict())

    client_secret = None
    if STRIPE_API_KEY:
        try:
            # Minimal Stripe PaymentIntent
            r = requests.post(
                "https://api.stripe.com/v1/payment_intents",
                data={"amount": total, "currency": currency, "automatic_payment_methods[enabled]": True},
                headers={"Authorization": f"Bearer {STRIPE_API_KEY}"},
                timeout=10,
            )
            if r.ok:
                client_secret = r.json().get("client_secret")
        except Exception:
            client_secret = None

    return CheckoutInitResponse(client_secret=client_secret, order_id=str(order_id), total_cents=total)

class CheckoutConfirmRequest(BaseModel):
    order_id: str
    provider: str = "stripe"  # or paypal; in this demo we assume already paid

class CheckoutConfirmResponse(BaseModel):
    order_id: str
    codes: List[str]

@app.post("/api/checkout/confirm", response_model=CheckoutConfirmResponse)
async def checkout_confirm(payload: CheckoutConfirmRequest):
    # In this simplified environment, we'll auto-fulfill and mark as paid
    # Allocate codes
    # fetch order
    orders = await get_documents("order", {"_id": {"$oid": payload.order_id}}, limit=1)
    if not orders:
        raise HTTPException(404, "Order not found")
    order = orders[0]
    allocated_codes: List[str] = []
    for item in order.get("items", []):
        product_id = item.get("product_id")
        qty = int(item.get("quantity", 1))
        available = await find_available_codes(product_id, qty)
        if len(available) < qty:
            raise HTTPException(409, "Insufficient stock for a product")
        for i in range(qty):
            code_doc = available[i]
            allocated_codes.append(code_doc["code"])
            # In a full system we'd update codekey assigned=true, order_id, and update order status.
    # Return codes immediately and pretend email sent
    return CheckoutConfirmResponse(order_id=payload.order_id, codes=allocated_codes)

# Orders
@app.get("/api/orders", response_model=List[dict])
async def list_orders(current=Depends(get_current_user)):
    q = {"email": current["email"]} if current["role"] != "admin" else {}
    docs = await get_documents("order", q, limit=50)
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs

# Contact
@app.post("/api/contact", response_model=dict)
async def contact(msg: ContactMessage):
    # For demo, simply persist and return ok
    now = datetime.utcnow()
    res = await create_document("contact", {**msg.dict(), "created_at": now})
    return {"ok": True, "id": str(res)}
