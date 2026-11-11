from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from database import Base, engine

# 1. Tabela de Municípios
class Municipio(Base):
    __tablename__ = "municipios"

    codigo_ibge = Column(String, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    populacao = Column(Integer, nullable=True)

    # Relação: um município tem vários casos
    casos = relationship("CasoDengue", back_populates="municipio")

# 2. Tabela de Casos de Dengue
class CasoDengue(Base):
    __tablename__ = "casos_dengue"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    codigo_ibge = Column(String, ForeignKey("municipios.codigo_ibge"))
    ano = Column(Integer, nullable=False)
    semana_epidemiologica = Column(Integer, nullable=False)
    quantidade_casos = Column(Integer, default=0)

    # Relação de volta para o município
    municipio = relationship("Municipio", back_populates="casos")

# 3. O comando mágico para criar tudo no Supabase!
if __name__ == "__main__":
    print("A enviar a estrutura para o Supabase...")
    Base.metadata.create_all(bind=engine)
    print("Tabelas criadas com sucesso no banco de dados! 🎉")