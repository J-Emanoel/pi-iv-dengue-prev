import pandas as pd
from pathlib import Path
from database import SessionLocal
from models import Municipio, CasoDengue

def carregar_dados_para_nuvem():
    # 1. Encontrar o ficheiro CSV (mesmo caminho que usaste no Streamlit)
    print("⏳ A procurar e ler o ficheiro CSV...")
    caminho_csv = Path(__file__).resolve().parent.parent / "data" / "interim" / "sinan_es_municipio_semana.csv"
    
    if not caminho_csv.exists():
        print(f"❌ Erro: Não encontrei o ficheiro em {caminho_csv}")
        return

    # Lê o CSV
    df = pd.read_csv(caminho_csv)
    
    # Tratamento igual ao teu app.py
    df['codigo_municipio'] = pd.to_numeric(df['codigo_municipio'], errors='coerce')
    df = df[df['codigo_municipio'].astype(str).str.startswith('32')].copy()
    df['codigo_municipio'] = df['codigo_municipio'].astype(int).astype(str)
    
    df['semana_epidemiologica'] = pd.to_numeric(df['semana_epidemiologica'], errors='coerce').fillna(0).astype(int)
    df['semana_num'] = df['semana_epidemiologica'].astype(str).str.zfill(6).str.slice(-2).astype(int)
    df['registos'] = df['registos'].fillna(0).astype(int)

    # 2. Abrir ligação ao banco
    db = SessionLocal()
    
    try:
        print("⏳ A registar os Municípios no Supabase...")
        municipios_unicos = df['codigo_municipio'].unique()
        for cod in municipios_unicos:
            # Verifica se o município já existe para não duplicar
            existe = db.query(Municipio).filter(Municipio.codigo_ibge == cod).first()
            if not existe:
                # Regista o município (usamos um nome genérico por agora, pode ser ajustado depois)
                novo_mun = Municipio(codigo_ibge=cod, nome=f"ES - {cod}")
                db.add(novo_mun)
        db.commit()
        print("✅ Municípios registados com sucesso!")

        print("⏳ A enviar o histórico de Casos de Dengue (isto pode demorar uns segundos/minutos)...")
        casos_para_inserir = []
        for index, linha in df.iterrows():
            caso = CasoDengue(
                codigo_ibge=linha['codigo_municipio'],
                ano=int(linha['ano_arquivo']),
                semana_epidemiologica=int(linha['semana_num']),
                quantidade_casos=int(linha['registos'])
            )
            casos_para_inserir.append(caso)
            
        # Inserimos tudo de uma vez (bulk) para ser muito mais rápido!
        db.bulk_save_objects(casos_para_inserir)
        db.commit()
        
        print(f"🎉 SUCESSO! {len(casos_para_inserir)} registos de dengue foram guardados no Supabase!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Ocorreu um erro ao guardar no banco: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    carregar_dados_para_nuvem()