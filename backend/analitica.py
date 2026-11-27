"""Calendário, junções semanais e diagnóstico de presença dos dados disponíveis."""

from datetime import timedelta

from sqlalchemy import Column, MetaData, Table, and_, case, func, inspect, literal, select, text, true

from backend.models import (
    CasoDengue, ClimaSemanal, EstacaoMeteorologica, Municipio, NotificacaoEstadual, PopulacaoMunicipal,
    SemanaEpidemiologica, VinculoMunicipioEstacao,
)
from pipelines.calendario import inicio_ano_epidemiologico, semanas_no_ano

# Período da versão atual da base; ampliar exige revisar também as limitações.
ANOS = tuple(range(2020, 2027))
# Característica do pacote recebido, não uma inferência pela data do computador.
ANOS_PARCIAIS_SINAN = (2026,)
NOME_VISAO = "base_analitica_semanal"
NOME_VISAO_SESA = "base_analitica_sesa"
ANOS_SESA = tuple(range(2020, 2025))


def gerar_calendario():
    return [dict(
        ano=ano, semana_epidemiologica=semana,
        data_inicio=inicio_ano_epidemiologico(ano) + timedelta(weeks=semana - 1),
        data_fim=inicio_ano_epidemiologico(ano) + timedelta(weeks=semana - 1, days=6),
    ) for ano in ANOS for semana in range(1, semanas_no_ano(ano) + 1)]


def consulta_base(fonte="sinan"):
    """Uma linha por município/semana; todas as fontes opcionais usam LEFT JOIN."""
    calendario = SemanaEpidemiologica.__table__
    municipio = Municipio.__table__
    if fonte == "sinan":
        casos, anos = CasoDengue.__table__, ANOS
        quantidade = casos.c.quantidade_casos
        campos_fonte = [
            casos.c.id.is_not(None).label("registro_sinan_presente"),
            literal("registros_notificados_sinan").label("tipo_numerador"),
            calendario.c.ano.in_(ANOS_PARCIAIS_SINAN).label("ano_fonte_sinan_parcial"),
        ]
    elif fonte == "sesa":
        casos, anos = NotificacaoEstadual.__table__, ANOS_SESA
        quantidade = casos.c.registros_notificados
        campos_fonte = [
            casos.c.codigo_ibge.is_not(None).label("registro_sesa_presente"),
            literal("registros_notificados_sesa").label("tipo_numerador"),
            literal(False).label("ano_fonte_sesa_parcial"),
            literal("sesa_esus_vs").label("fonte_serie"),
            literal("DATA_NOTIFICACAO").label("data_referencia_registros"),
            casos.c.fonte_url.label("fonte_registros_url"),
            casos.c.fonte_manifesto_sha256.label("fonte_registros_manifesto_sha256"),
            casos.c.fonte_csv_sha256.label("fonte_registros_csv_sha256"),
        ]
    else:
        raise ValueError("Fonte analítica desconhecida; use sinan ou sesa.")
    populacao = PopulacaoMunicipal.__table__
    vinculo = VinculoMunicipioEstacao.__table__
    estacao = EstacaoMeteorologica.__table__
    clima = ClimaSemanal.__table__
    fontes = calendario.join(municipio, true()).outerjoin(casos, and_(
        casos.c.codigo_ibge == municipio.c.codigo_ibge, casos.c.ano == calendario.c.ano,
        casos.c.semana_epidemiologica == calendario.c.semana_epidemiologica,
    )).outerjoin(populacao, and_(
        populacao.c.codigo_ibge == municipio.c.codigo_ibge, populacao.c.ano == calendario.c.ano,
    )).outerjoin(vinculo, and_(
        vinculo.c.codigo_ibge == municipio.c.codigo_ibge, vinculo.c.ano == calendario.c.ano,
    )).outerjoin(estacao, estacao.c.codigo == vinculo.c.codigo_estacao).outerjoin(clima, and_(
        clima.c.codigo_estacao == vinculo.c.codigo_estacao, clima.c.ano == calendario.c.ano,
        clima.c.semana_epidemiologica == calendario.c.semana_epidemiologica,
    ))
    coberturas = [
        (100.0 * clima.c[horas] / func.nullif(clima.c.horas_previstas, 0)).label(nome)
        for horas, nome in (
            ("horas_precipitacao", "cobertura_precipitacao_pct"),
            ("horas_temperatura", "cobertura_temperatura_pct"),
            ("horas_umidade", "cobertura_umidade_pct"),
        )
    ]
    return select(
        municipio.c.codigo_ibge, municipio.c.nome.label("nome_municipio"),
        calendario.c.ano, calendario.c.semana_epidemiologica, calendario.c.data_inicio, calendario.c.data_fim,
        quantidade.label("registros_notificados"), *campos_fonte,
        literal(False).label("cobertura_epidemiologica_validada"),
        func.coalesce(populacao.c.codigo_ibge_completo, vinculo.c.codigo_ibge_completo).label("codigo_ibge_completo"),
        populacao.c.populacao,
        populacao.c.data_referencia.label("data_referencia_populacao"),
        populacao.c.tipo.label("tipo_populacao"), populacao.c.fonte_url.label("fonte_populacao_url"),
        populacao.c.fonte_sha256.label("fonte_populacao_sha256"),
        populacao.c.observacao.label("observacao_populacao"),
        case((populacao.c.populacao > 0,
              quantidade * 100000.0 / func.nullif(populacao.c.populacao, 0)),
             else_=None).label("registros_por_100_mil"),
        vinculo.c.codigo_estacao, estacao.c.nome.label("nome_estacao"), vinculo.c.distancia_km,
        vinculo.c.metodo.label("metodo_vinculo"), vinculo.c.observacao.label("observacao_vinculo"),
        vinculo.c.fonte_geografia_url, vinculo.c.fonte_geografia_sha256, vinculo.c.fonte_inmet_sha256,
        literal(False).label("representatividade_climatica_validada"),
        clima.c.codigo_estacao.is_not(None).label("clima_presente"),
        clima.c.precipitacao_mm, clima.c.temperatura_media_c, clima.c.umidade_media_pct,
        clima.c.horas_observadas, clima.c.horas_previstas, clima.c.horas_precipitacao,
        clima.c.horas_temperatura, clima.c.horas_umidade, *coberturas, clima.c.fuso,
    ).select_from(fontes).where(calendario.c.ano.in_(anos), municipio.c.codigo_ibge.like("32____"))


# Descreve a visão para consultas; fica fora do metadata das tabelas físicas.
BASE_ANALITICA = Table(
    NOME_VISAO, MetaData(),
    *(Column(coluna.name, coluna.type) for coluna in consulta_base().selected_columns),
)
BASE_SESA = Table(
    NOME_VISAO_SESA, MetaData(),
    *(Column(coluna.name, coluna.type) for coluna in consulta_base("sesa").selected_columns),
)


def tabela_analitica(fonte):
    """Seleciona uma visão sem misturar registros de fontes diferentes."""
    tabelas = {"sinan": BASE_ANALITICA, "sesa": BASE_SESA}
    if fonte not in tabelas:
        raise ValueError("Fonte analítica desconhecida.")
    return tabelas[fonte]


def _filtrar_recorte(consulta, tabela, ano, codigo_municipio):
    if ano is not None:
        consulta = consulta.where(tabela.c.ano == ano)
    if codigo_municipio is not None:
        consulta = consulta.where(tabela.c.codigo_ibge == codigo_municipio)
    return consulta


def consulta_semanal(
    *, fonte="sinan", ano=None, codigo_municipio=None,
    semana=None, limite=500, deslocamento=0,
):
    """Histórico paginado e ordenado, com os mesmos filtros nas duas fontes."""
    tabela = tabela_analitica(fonte)
    consulta = _filtrar_recorte(tabela.select(), tabela, ano, codigo_municipio)
    if semana is not None:
        consulta = consulta.where(tabela.c.semana_epidemiologica == semana)
    return (
        consulta.order_by(tabela.c.data_inicio, tabela.c.codigo_ibge)
        .limit(limite).offset(deslocamento)
    )


def preparar_base_analitica(engine, *, fonte="sinan"):
    """Acrescenta o calendário e cria a visão sem modificar os dados das fontes."""
    calendario = SemanaEpidemiologica.__table__
    consulta = consulta_base(fonte)
    modelo = CasoDengue if fonte == "sinan" else NotificacaoEstadual
    tabela_base = BASE_ANALITICA if fonte == "sinan" else BASE_SESA
    anos = ANOS if fonte == "sinan" else ANOS_SESA
    nome_visao = NOME_VISAO if fonte == "sinan" else NOME_VISAO_SESA
    fontes = (Municipio, modelo, PopulacaoMunicipal, EstacaoMeteorologica, ClimaSemanal, VinculoMunicipioEstacao)
    semanas = gerar_calendario()
    semanas_no_periodo = sum(row["ano"] in anos for row in semanas)
    with engine.begin() as connection:
        if connection.dialect.name not in ("postgresql", "sqlite"):
            raise ValueError("Base analítica preparada somente para PostgreSQL ou SQLite.")
        if connection.dialect.name == "sqlite" and not connection.connection.driver_connection.in_transaction:
            # Inclui DDL na transação também no modo legado do sqlite3.
            connection.exec_driver_sql("BEGIN")
        inspector = inspect(connection)
        if any(not inspector.has_table(model.__tablename__) for model in fontes):
            raise ValueError("Prepare primeiro as tabelas de municípios, dengue, população, clima e vínculos.")
        if nome_visao in inspector.get_table_names():
            raise ValueError("Já existe uma tabela física com o nome reservado à visão analítica.")
        calendario.create(bind=connection, checkfirst=True)
        if connection.dialect.name == "postgresql":
            connection.execute(text(
                "LOCK TABLE calendario_epidemiologico IN SHARE ROW EXCLUSIVE MODE"
            ))
            connection.execute(text(
                f"LOCK TABLE municipios, {modelo.__tablename__}, populacoes_municipais, estacoes_inmet, "
                "clima_semanal, municipios_estacoes IN SHARE MODE"
            ))
        atuais = {(row.ano, row.semana_epidemiologica): dict(row._mapping)
                  for row in connection.execute(select(calendario).where(calendario.c.ano.in_(ANOS)))}
        esperado = {(row["ano"], row["semana_epidemiologica"]): row for row in semanas}
        if any(chave not in esperado or row != esperado[chave] for chave, row in atuais.items()):
            raise ValueError("Calendário existente incompatível; revise antes de substituir datas.")
        novas = [row for chave, row in esperado.items() if chave not in atuais]
        if novas:
            connection.execute(calendario.insert(), novas)
        sql = str(consulta.compile(dialect=connection.dialect, compile_kwargs={"literal_binds": True}))
        if connection.dialect.name == "postgresql":
            # Herda as permissões das fontes ao consultar pelo PostgREST/Supabase.
            opcao = " WITH (security_invoker = true)" if connection.dialect.server_version_info >= (15,) else ""
            connection.exec_driver_sql(f"CREATE OR REPLACE VIEW {nome_visao}{opcao} AS {sql}")
        else:
            connection.exec_driver_sql(f"DROP VIEW IF EXISTS {nome_visao}")
            connection.exec_driver_sql(f"CREATE VIEW {nome_visao} AS {sql}")
        base = tabela_base.c
        total = connection.scalar(select(func.count()).select_from(tabela_base))
        municipios = connection.scalar(select(func.count()).select_from(Municipio).where(Municipio.codigo_ibge.like("32____")))
        if not municipios:
            raise ValueError("Cadastre os municípios do ES antes de preparar a base analítica.")
        if total != municipios * semanas_no_periodo:
            raise ValueError("As junções multiplicaram linhas; revise as chaves das fontes.")
        casos = modelo.__table__
        quantidade = casos.c.quantidade_casos if fonte == "sinan" else casos.c.registros_notificados
        presentes, notificacoes = connection.execute(select(
            func.count(), func.sum(quantidade),
        ).select_from(casos).where(casos.c.ano.in_(anos), casos.c.codigo_ibge.like("32____"))).one()
        integrados = connection.execute(select(
            func.count(base.registros_notificados), func.sum(base.registros_notificados),
        )).one()
        if integrados != (presentes, notificacoes):
            raise ValueError("A base analítica perdeu ou multiplicou notificações; a preparação foi revertida.")
    return dict(visao=nome_visao, semanas_calendario=semanas_no_periodo, semanas_inseridas=len(novas),
                linhas=total, **{f"linhas_{fonte}": presentes}, registros_notificados=notificacoes)


def consulta_cobertura(
    cobertura_minima_clima_pct=80.0, *, fonte="sinan", ano=None, codigo_municipio=None,
):
    """Diagnóstico de presença; percentual de semanas não mede completude epidemiológica."""
    tabela = tabela_analitica(fonte)
    b = tabela.c
    presenca = b[f"registro_{fonte}_presente"]
    parcial = b[f"ano_fonte_{fonte}_parcial"]
    def contar(condicao):
        return func.sum(case((condicao, 1), else_=0))
    sensores = and_(
        b.horas_precipitacao > 0, b.horas_temperatura > 0, b.horas_umidade > 0,
        b.cobertura_precipitacao_pct >= cobertura_minima_clima_pct,
        b.cobertura_temperatura_pct >= cobertura_minima_clima_pct,
        b.cobertura_umidade_pct >= cobertura_minima_clima_pct,
    )
    consulta = select(
        b.codigo_ibge, b.nome_municipio, b.ano, parcial,
        b.cobertura_epidemiologica_validada, b.representatividade_climatica_validada,
        func.count().label("semanas_calendario"),
        contar(presenca).label(f"semanas_com_registros_{fonte}"),
        contar(b.registros_notificados.is_(None)).label(f"semanas_sem_registros_{fonte}"),
        func.sum(b.registros_notificados).label("registros_notificados"),
        (100.0 * contar(presenca) / func.count()).label(f"presenca_semanas_{fonte}_pct"),
        contar(b.populacao.is_not(None)).label("semanas_com_populacao"),
        contar(b.codigo_estacao.is_not(None)).label("semanas_com_vinculo"),
        contar(b.clima_presente).label("semanas_com_linha_clima"),
        contar(sensores).label("semanas_clima_cobertura_suficiente"),
        contar(and_(sensores, presenca, b.populacao.is_not(None))).label("semanas_com_fontes_e_cobertura"),
        literal(float(cobertura_minima_clima_pct)).label("cobertura_minima_clima_pct"),
    ).select_from(tabela).group_by(
        b.codigo_ibge, b.nome_municipio, b.ano, parcial,
        b.cobertura_epidemiologica_validada, b.representatividade_climatica_validada,
    )
    return _filtrar_recorte(consulta, tabela, ano, codigo_municipio).order_by(b.ano, b.codigo_ibge)
