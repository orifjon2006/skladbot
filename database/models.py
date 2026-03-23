from datetime import datetime
from sqlalchemy import String, Integer, BigInteger, Float, ForeignKey, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

# Barcha modellar uchun asosiy sinf
class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default="customer") # admin, operator, customer

class Product(Base):
    __tablename__ = 'products'
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150))
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True) # Qidiruv tez bo'lishi uchun index=True
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    price: Mapped[float] = mapped_column(Float, default=0.0)

class Customer(Base):
    __tablename__ = 'customers'
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20), nullable=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=True, index=True)
    balance: Mapped[float] = mapped_column(Float, default=0.0) # Manfiy bo'lsa qarzdor

class Order(Base):
    __tablename__ = 'orders'
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'))
    total_price: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="new") # new, confirmed, delivered, cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Bog'lanishlar (Order o'chirilsa, uning ichidagi mahsulotlar va to'lovlar ham o'chadi)
    customer = relationship("Customer", backref="orders")
    items = relationship("OrderItem", backref="order", cascade="all, delete-orphan")
    payments = relationship("Payment", backref="order", cascade="all, delete-orphan")
    receipt_code: Mapped[str] = mapped_column(String(6), unique=True, nullable=True) 
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")

class OrderItem(Base):
    __tablename__ = 'order_items'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id', ondelete='CASCADE'))
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete='RESTRICT'))
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)

    # Ko'prikning ikkinchi uchi (Xato shu qator yo'qligidan chiqayotgan edi)
    order: Mapped["Order"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()
class Payment(Base):
    __tablename__ = 'payments'
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('customers.id', ondelete='CASCADE'))
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    customer = relationship("Customer", backref="payments")

