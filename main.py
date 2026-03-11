import os
from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timedelta
from typing import Optional, List
from passlib.context import CryptContext
from jose import JWTError, jwt
from groq import Groq
import uvicorn
import json
from dotenv import load_dotenv

load_dotenv()

# ===== CONFIGURATION =====
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/mydatabase")
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# ===== DATABASE SETUP =====
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ===== GROQ API SETUP =====
groq_client = Groq(api_key="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")

# ===== SECURITY =====
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# ===== DATABASE MODELS =====
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="buyer")  # buyer, seller, admin
    created_at = Column(DateTime, default=datetime.utcnow)

class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, index=True)
    description = Column(Text)
    price = Column(Float)
    quantity = Column(Integer)
    marketplace = Column(String)  # Kaspi.kz, Wildberries, Ozon
    photo_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    views = Column(Integer, default=0)

class Sale(Base):
    __tablename__ = "sales"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    buyer_id = Column(Integer, ForeignKey("users.id"))
    seller_id = Column(Integer, ForeignKey("users.id"))
    quantity = Column(Integer)
    total_price = Column(Float)
    status = Column(String, default="pending")  # pending, completed, cancelled
    created_at = Column(DateTime, default=datetime.utcnow)

class ViewHistory(Base):
    __tablename__ = "view_history"
    
    id = Column(Integer, primary_key=True, index=True)
    buyer_id = Column(Integer, ForeignKey("users.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    viewed_at = Column(DateTime, default=datetime.utcnow)

class GenerationHistory(Base):
    __tablename__ = "generation_history"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    product_name = Column(String)
    marketplace = Column(String)
    description = Column(Text)
    words_count = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

# Create all tables
Base.metadata.create_all(bind=engine)

# ===== PYDANTIC MODELS =====
class UserRegister(BaseModel):
    email: EmailStr
    username: str
    password: str
    role: str = "buyer"

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    role: str

class ProductCreate(BaseModel):
    name: str
    price: float
    quantity: int
    marketplace: str

class ProductResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    price: float
    quantity: int
    marketplace: str
    views: int
    
    class Config:
        from_attributes = True

class SaleCreate(BaseModel):
    product_id: int
    quantity: int

class SaleResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    total_price: float
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class GenerateDescriptionRequest(BaseModel):
    name: str
    features: str
    marketplace: str

class StatsResponse(BaseModel):
    total_sales: int
    total_revenue: float
    popular_products: List[dict]
    daily_sales: List[dict]

# ===== HELPER FUNCTIONS =====
def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

# ===== FASTAPI APP =====
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== AUTH ENDPOINTS =====
@app.post("/auth/register", response_model=Token)
async def register(user: UserRegister, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already taken")
    
    hashed_password = get_password_hash(user.password)
    db_user = User(email=user.email, username=user.username, hashed_password=hashed_password, role=user.role)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.username}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer", "user_id": db_user.id, "role": db_user.role}

@app.post("/auth/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer", "user_id": user.id, "role": user.role}

# ===== SELLER ENDPOINTS =====
@app.post("/seller/products", response_model=ProductResponse)
async def create_product(product: ProductCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "seller":
        raise HTTPException(status_code=403, detail="Only sellers can create products")
    
    db_product = Product(
        seller_id=current_user.id,
        name=product.name,
        price=product.price,
        quantity=product.quantity,
        marketplace=product.marketplace
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

@app.get("/seller/products", response_model=List[ProductResponse])
async def get_seller_products(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "seller":
        raise HTTPException(status_code=403, detail="Only sellers can view their products")
    
    products = db.query(Product).filter(Product.seller_id == current_user.id).all()
    return products

@app.get("/seller/stats", response_model=StatsResponse)
async def get_seller_stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "seller":
        raise HTTPException(status_code=403, detail="Only sellers can view stats")
    
    sales = db.query(Sale).filter(Sale.seller_id == current_user.id).all()
    products = db.query(Product).filter(Product.seller_id == current_user.id).all()
    
    total_sales = len(sales)
    total_revenue = sum(s.total_price for s in sales)
    
    popular_products = []
    for product in products:
        product_sales = len([s for s in sales if s.product_id == product.id])
        popular_products.append({"name": product.name, "sales": product_sales})
    
    popular_products.sort(key=lambda x: x["sales"], reverse=True)
    
    return {
        "total_sales": total_sales,
        "total_revenue": total_revenue,
        "popular_products": popular_products[:5],
        "daily_sales": []
    }

@app.get("/seller/recommendations")
async def get_recommendations(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "seller":
        raise HTTPException(status_code=403, detail="Only sellers can view recommendations")
    
    try:
        products = db.query(Product).filter(Product.seller_id == current_user.id).all()
        sales = db.query(Sale).filter(Sale.seller_id == current_user.id).all()
        
        product_list = [f"{p.name} (продано: {len([s for s in sales if s.product_id == p.id])})" for p in products]
        
        prompt = f"""
        Ты эксперт по маркетплейсам. Проанализируй данные продавца и дай рекомендации:
        Товары: {', '.join(product_list)}
        
        Рекомендации:
        1. Какие товары стоит закупить больше?
        2. Какие товары имеют низкий спрос и стоит убрать?
        3. Какие товары можно комбинировать?
        """
        
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Ты эксперт по маркетплейсам и e-commerce."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500,
        )
        
        return {"recommendations": response.choices[0].message.content}
    except Exception as e:
        return {"recommendations": f"Ошибка: {str(e)}"}

# ===== BUYER ENDPOINTS =====
@app.get("/buyer/catalog", response_model=List[ProductResponse])
async def get_catalog(marketplace: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Product).filter(Product.quantity > 0)
    if marketplace:
        query = query.filter(Product.marketplace == marketplace)
    
    products = query.all()
    
    for product in products:
        product.views += 1
    db.commit()
    
    return products

@app.post("/buyer/purchase")
async def purchase(sale: SaleCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "buyer":
        raise HTTPException(status_code=403, detail="Only buyers can make purchases")
    
    product = db.query(Product).filter(Product.id == sale.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    if product.quantity < sale.quantity:
        raise HTTPException(status_code=400, detail="Not enough stock")
    
    total_price = product.price * sale.quantity
    
    db_sale = Sale(
        product_id=sale.product_id,
        buyer_id=current_user.id,
        seller_id=product.seller_id,
        quantity=sale.quantity,
        total_price=total_price,
        status="completed"
    )
    
    product.quantity -= sale.quantity
    
    db.add(db_sale)
    db.commit()
    db.refresh(db_sale)
    
    return {"message": "Purchase successful", "order_id": db_sale.id, "total": total_price}

@app.get("/buyer/recommendations")
async def get_buyer_recommendations(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "buyer":
        raise HTTPException(status_code=403, detail="Only buyers can view recommendations")
    
    view_history = db.query(ViewHistory).filter(ViewHistory.buyer_id == current_user.id).all()
    viewed_product_ids = [v.product_id for v in view_history]
    
    recommendations = db.query(Product).filter(
        Product.id.notin_(viewed_product_ids) if viewed_product_ids else True,
        Product.quantity > 0
    ).limit(5).all()
    
    return {"recommendations": [{"id": p.id, "name": p.name, "price": p.price, "marketplace": p.marketplace} for p in recommendations]}

# ===== DESCRIPTION GENERATION =====
@app.post("/generate-description")
async def generate_description(data: GenerateDescriptionRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        prompt = f"""
        Ты эксперт по маркетплейсам {data.marketplace}.
        Напиши продающее SEO-описание для товара.
        Название: {data.name}
        Характеристики: {data.features}
        Пиши на русском языке, структурировано, используй списки.
        """
        
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Ты эксперт-копирайтер для маркетплейсов."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1024,
        )
        
        description = completion.choices[0].message.content
        words_count = len(description.split())
        
        generation = GenerationHistory(
            user_id=current_user.id,
            product_name=data.name,
            marketplace=data.marketplace,
            description=description,
            words_count=words_count
        )
        db.add(generation)
        db.commit()
        
        return {"description": description, "words_count": words_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

# ===== ADMIN ENDPOINTS =====
@app.get("/admin/stats")
async def get_admin_stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can view stats")
    
    total_users = db.query(User).count()
    total_sellers = db.query(User).filter(User.role == "seller").count()
    total_buyers = db.query(User).filter(User.role == "buyer").count()
    total_products = db.query(Product).count()
    total_sales = db.query(Sale).count()
    total_revenue = sum(s.total_price for s in db.query(Sale).all()) or 0
    
    return {
        "total_users": total_users,
        "total_sellers": total_sellers,
        "total_buyers": total_buyers,
        "total_products": total_products,
        "total_sales": total_sales,
        "total_revenue": total_revenue
    }

@app.get("/admin/ai-monitor")
async def monitor_ai(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can monitor AI")
    
    generations = db.query(GenerationHistory).all()
    total_generations = len(generations)
    total_words_generated = sum(g.words_count for g in generations)
    
    return {
        "total_generations": total_generations,
        "total_words_generated": total_words_generated,
        "avg_words_per_generation": total_words_generated // max(total_generations, 1)
    }

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
