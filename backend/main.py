from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
import models
from database import engine, get_db

# Inicializa o FastAPI
app = FastAPI(
    title="API DenguePrev - ES",
    description="API para fornecimento de dados epidemiológicos e climáticos",
    version="1.0.0"
)

# Rota 1: Raiz (Apenas para testar se está online)
@app.get("/")
def home():
    return {"mensagem": "Bem-vindo à API do DenguePrev! O servidor está a correr perfeitamente."}

# Rota 2: Buscar todos os municípios gravados no banco
@app.get("/municipios")
def listar_municipios(db: Session = Depends(get_db)):
    # Faz uma query à tabela de Municípios no Supabase
    municipios = db.query(models.Municipio).all()
    return municipios

# Rota 3: Buscar o histórico de casos de dengue
@app.get("/casos")
def listar_casos(db: Session = Depends(get_db)):
    # Faz uma query à tabela de Casos no Supabase
    casos = db.query(models.CasoDengue).all()
    return casos