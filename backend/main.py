from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, func
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

DATABASE_URL = "sqlite:///vigia.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(bind=engine)
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
# SCHEMA API
# ==============================

class Produto(BaseModel):
    produto: str
    quantidade: int
    preco_unitario: float
    lote: str
    validade: str
    funcionario: str

# ==============================
# CALCULO DESCONTO
# ==============================

def calcular_desconto(dias_restantes, quantidade):

    if dias_restantes >= 7:
        desconto = 10
    elif dias_restantes >= 5:
        desconto = 20
    elif dias_restantes >= 3:
        desconto = 30
    elif dias_restantes == 2:
        desconto = 40
    elif dias_restantes == 1:
        desconto = 60
    else:
        desconto = 80

    if quantidade > 50:
        desconto += 20
    elif quantidade > 20:
        desconto += 10

    if desconto > 90:
        desconto = 90

    return desconto

# ==============================
# GERAR MENSAGEM ALERTA
# ==============================

def gerar_mensagem_alerta(produtos):

    mensagem = "⚠ ALERTA VIGIA BR\n\n"
    mensagem += "Produtos próximos de vencer:\n\n"

    for p in produtos:
        mensagem += (
            f"• {p['produto']}\n"
            f"Quantidade: {p['quantidade']}\n"
            f"Vence em: {p['dias_restantes']} dias\n\n"
        )

    mensagem += "Verifique promoções imediatamente."

    return mensagem

# ==============================
# ENVIAR EMAIL
# ==============================

def enviar_email_alerta(mensagem):

    if not EMAIL_REMETENTE:
        print("Email não configurado")
        return

    msg = MIMEText(mensagem)

    msg["Subject"] = "⚠ Alerta Vigia BR"
    msg["From"] = EMAIL_REMETENTE
    msg["To"] = EMAIL_DESTINO

    servidor = smtplib.SMTP_SSL("smtp.gmail.com", 465)

    servidor.login(EMAIL_REMETENTE, EMAIL_SENHA)

    servidor.sendmail(
        EMAIL_REMETENTE,
        EMAIL_DESTINO,
        msg.as_string()
    )

    servidor.quit()

# ==============================
# ENVIAR WHATSAPP
# ==============================

def enviar_whatsapp_alerta(mensagem):

    if not WHATSAPP_PHONE or not WHATSAPP_APIKEY:
        print("WhatsApp não configurado")
        return

    texto = urllib.parse.quote(mensagem)

    url = f"https://api.callmebot.com/whatsapp.php?phone={WHATSAPP_PHONE}&text={texto}&apikey={WHATSAPP_APIKEY}"

    requests.get(url)

# ==============================
# FUNÇÃO CENTRAL DE ALERTA
# ==============================

def verificar_produtos_e_enviar_alerta():

    db = SessionLocal()

    hoje = datetime.now().date()
    limite = hoje + timedelta(days=7)

    produtos = db.query(ProdutoDB).all()

    criticos = []

    for p in produtos:

        try:
            data_validade = datetime.strptime(p.validade, "%Y-%m-%d").date()
        except:
            continue

        if hoje <= data_validade <= limite:

            dias_restantes = (data_validade - hoje).days

            criticos.append({
                "produto": p.produto,
                "quantidade": p.quantidade,
                "dias_restantes": dias_restantes
            })

    db.close()

    if len(criticos) == 0:
        print("Nenhum produto próximo da validade hoje.")
        return {"mensagem": "Nenhum produto crítico"}

    mensagem = gerar_mensagem_alerta(criticos)

    enviar_email_alerta(mensagem)
    enviar_whatsapp_alerta(mensagem)

    print("Alerta enviado!")

    return {
        "status": "alerta enviado",
        "produtos_alertados": len(criticos)
    }

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
    db.close()

    return {"status": "produto registrado"}

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
# RANKING
# ==============================

@app.get("/ranking")
def ranking_funcionarios():

    db = SessionLocal()

    ranking = db.query(
        ProdutoDB.funcionario,
        func.count(ProdutoDB.id).label("registros")
    ).group_by(
        ProdutoDB.funcionario
    ).order_by(
        func.count(ProdutoDB.id).desc()
    ).all()

    resultado = []

    for r in ranking:
        resultado.append({
            "funcionario": r.funcionario,
            "registros": r.registros
        })

    db.close()

    return resultado

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
            data_validade = datetime.strptime(p.validade, "%Y-%m-%d").date()
        except:
            continue

        if hoje <= data_validade <= limite:

            dias_restantes = (data_validade - hoje).days

            desconto = calcular_desconto(
                dias_restantes,
                p.quantidade
            )

            resultado.append({
                "produto": p.produto,
                "quantidade": p.quantidade,
                "validade": p.validade,
                "dias_restantes": dias_restantes,
                "funcionario": p.funcionario,
                "desconto_sugerido": desconto,
                "preco_unitario": p.preco_unitario
            })

    db.close()

    return resultado

# ==============================
# IMPACTO FINANCEIRO
# ==============================

@app.get("/impacto-financeiro")
def impacto_financeiro():

    db = SessionLocal()

    produtos = db.query(ProdutoDB).all()

    perda_total = 0
    receita_promocao = 0

    hoje = datetime.now().date()

    for p in produtos:

        try:
            data_validade = datetime.strptime(p.validade, "%Y-%m-%d").date()
        except:
            continue

        dias_restantes = (data_validade - hoje).days

        if dias_restantes <= 7:

            perda = p.quantidade * p.preco_unitario

            desconto = calcular_desconto(
                dias_restantes,
                p.quantidade
            )

            preco_promo = p.preco_unitario * (1 - desconto/100)

            receita = preco_promo * p.quantidade

            perda_total += perda
            receita_promocao += receita

    db.close()

    perda_evitada = perda_total - receita_promocao

    return {
        "perda_total": round(perda_total,2),
        "receita_promocao": round(receita_promocao,2),
        "perda_evitada": round(perda_evitada,2)
    }

# ==============================
# ALERTA MANUAL
# ==============================

@app.get("/enviar-alerta")
def enviar_alerta():
    return verificar_produtos_e_enviar_alerta()

# ==============================
# ALERTA AUTOMÁTICO 08:00
# ==============================

scheduler = BackgroundScheduler()

def alerta_diario():
    print("Executando verificação automática...")
    verificar_produtos_e_enviar_alerta()

scheduler.add_job(alerta_diario, "cron", hour=8, minute=0)

scheduler.start()