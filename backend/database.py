import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

# 1. Diz ao Python para procurar o .env AQUI NA MESMA PASTA (backend)
env_path = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path=env_path)

# 2. Pega na URL do banco de dados
db_url = os.getenv("DATABASE_URL")

# --- VERIFICAÇÃO PARA O TERMINAL ---
if db_url is None:
    print("❌ ERRO: O Python não encontrou a variável DATABASE_URL.")
else:
    print("✅ URL do Supabase encontrada com sucesso!")
    
# O SQLAlchemy pede o prefixo postgresql+psycopg2:// para usar o driver correto
if db_url and db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

# 3. Cria o "motor" de conexão com o Supabase
engine = create_engine(db_url)

# 4. Configura a sessão
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 5. Base para criar as tabelas
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()