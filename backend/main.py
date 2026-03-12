from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime, timedelta

import smtplib
from email.mime.text import MIMEText
import requests
import urllib.parse

from dotenv import load_dotenv
import os

from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()

app = FastAPI()

# ==============================
# CORS
# ==============================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================
# CONFIG EMAIL / WHATSAPP
# ==============================

EMAIL_REMETENTE = os.getenv("EMAIL_REMETENTE")
EMAIL_SENHA = os.getenv("EMAIL_SENHA")
EMAIL_DESTINO = os.getenv("EMAIL_DESTINO")

WHATSAPP_PHONE = os.getenv("WHATSAPP_PHONE")
WHATSAPP_APIKEY = os.getenv("WHATSAPP_APIKEY")

# ==============================
# CONFIG BANCO
# ==============================

DATABASE_URL = os.getenv("DATABASE_URL")

# correção necessária no Render
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()

# ==============================
# MODELO BANCO
# ==============================

class ProdutoDB(Base):

    __tablename__ = "produtos"

    id = Column(Integer, primary_key=True, index=True)
    produto = Column(String)
    quantidade = Column(Integer)
    preco_unitario = Column(Float)
    lote = Column(String)
    validade = Column(String)
    funcionario = Column(String)

Base.metadata.create_all(bind=engine)

# ==============================
# SCHEMA
# ==============================

class Produto(BaseModel):

    produto: str
    quantidade: int
    preco_unitario: float
    lote: str
    validade: str
    funcionario: str

# ==============================
# ROTAS
# ==============================

@app.get("/")
def home():
    return {"mensagem": "API Vigia BR funcionando"}

# ==============================
# CRIAR PRODUTO
# ==============================

@app.post("/produtos")
def criar_produto(produto: Produto):

    db = SessionLocal()

    novo_produto = ProdutoDB(
        produto=produto.produto,
        quantidade=produto.quantidade,
        preco_unitario=produto.preco_unitario,
        lote=produto.lote,
        validade=produto.validade,
        funcionario=produto.funcionario
    )

    db.add(novo_produto)
    db.commit()
    db.refresh(novo_produto)

    db.close()

    return {
        "status": "produto registrado",
        "id": novo_produto.id
    }

# ==============================
# LISTAR PRODUTOS
# ==============================

@app.get("/produtos")
def listar_produtos():

    db = SessionLocal()

    produtos = db.query(ProdutoDB).all()

    resultado = []

    for p in produtos:

        resultado.append({
            "id": p.id,
            "produto": p.produto,
            "quantidade": p.quantidade,
            "preco_unitario": p.preco_unitario,
            "lote": p.lote,
            "validade": p.validade,
            "funcionario": p.funcionario
        })

    db.close()

    return resultado

# ==============================
# EXCLUIR PRODUTO
# ==============================

@app.delete("/produtos/{produto_id}")
def excluir_produto(produto_id: int):

    db = SessionLocal()

    produto = db.query(ProdutoDB).filter(
        ProdutoDB.id == produto_id
    ).first()

    if not produto:

        db.close()

        return {"erro": "Produto não encontrado"}

    db.delete(produto)
    db.commit()

    db.close()

    return {"status": "produto excluído"}

# ==============================
# PRODUTOS EM RISCO
# ==============================

@app.get("/produtos-risco")
def produtos_em_risco():

    db = SessionLocal()

    hoje = datetime.now().date()
    limite = hoje + timedelta(days=7)

    produtos = db.query(ProdutoDB).all()

    resultado = []

    for p in produtos:

        try:
            data_validade = datetime.strptime(
                p.validade,
                "%Y-%m-%d"
            ).date()
        except:
            continue

        if hoje <= data_validade <= limite:

            dias_restantes = (data_validade - hoje).days

            resultado.append({
                "id": p.id,
                "produto": p.produto,
                "quantidade": p.quantidade,
                "validade": p.validade,
                "dias_restantes": dias_restantes,
                "funcionario": p.funcionario
            })

    db.close()

    return resultado