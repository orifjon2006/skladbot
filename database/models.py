from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default="customer", index=True)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    price: Mapped[float] = mapped_column(Float, default=0.0)

    order_items: Mapped[list["OrderItem"]] = relationship(back_populates="product")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True, index=True)
    balance: Mapped[float] = mapped_column(Float, default=0.0)

    orders: Mapped[list["Order"]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"),
        index=True,
    )
    total_price: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    receipt_code: Mapped[str | None] = mapped_column(String(6), unique=True, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    customer: Mapped["Customer"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        index=True,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"),
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)

    order: Mapped["Order"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship(back_populates="order_items")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"),
        index=True,
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    amount: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    customer: Mapped["Customer"] = relationship(back_populates="payments")
    order: Mapped["Order | None"] = relationship(back_populates="payments")
