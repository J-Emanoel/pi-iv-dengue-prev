import io
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, event, select, update

from backend.database import Base
from backend.models import ClimaSemanal, EstacaoMeteorologica, Municipio, VinculoMunicipioEstacao
from backend.povoar_banco import sincronizar_clima, sincronizar_vinculos
from pipelines.arquivos import sha256_arquivo
from pipelines.etl_inmet import ANOS, agregar_horas, carregar_clima, ler_arquivo, processar_pacote, validar_clima
from pipelines.vincular_estacoes import API_BASE, distancia_haversine, gerar_vinculos, validar_vinculos


METADATA = (
    "REGIAO:;SE\nUF:;ES\nESTACAO:;VITÓRIA\nCODIGO (WMO):;A612\n"
    "LATITUDE:;-20,27\nLONGITUDE:;-40,30\nALTITUDE:;9\nDATA DE FUNDACAO:;31/10/06\n"
)
HEADER = "Data;Hora UTC;PRECIPITAÇÃO TOTAL, HORÁRIO (mm);TEMPERATURA DO AR - BULBO SECO, HORARIA (°C);UMIDADE RELATIVA DO AR, HORARIA (%);\n"


def arquivo(rows, ano):
    return ler_arquivo((METADATA + HEADER + rows).encode("cp1252"), ano)


def fonte_clima():
    estacao, dados, _ = arquivo("2025/01/06;0300 UTC;0;20;50;\n2025/01/06;0400 UTC;2;30;60;\n", 2025)
    estacao["fonte_sha256"] = "a" * 64
    return [estacao], agregar_horas(dados, "a" * 64)


def dados_geograficos():
    cadastro = [dict(codigo_municipio="320530", codigo_ibge_completo="3205309")]
    pontos = [dict(codigo_ibge_completo="3205309", latitude=-20.27, longitude=-40.30,
                   fonte_url=f"{API_BASE}/3205309/metadados")]
    estacao = fonte_clima()[0][0]
    resumo = dict(entrada_sha256="a" * 64, arquivos=[dict(ano_arquivo=ano, metadados=estacao) for ano in ANOS])
    return cadastro, pontos, resumo


def fonte_vinculos():
    return gerar_vinculos(*dados_geograficos())


class VinculosTests(unittest.TestCase):
    def test_distancia_e_proximidade_por_ano_sem_estacao_indisponivel(self):
        self.assertAlmostEqual(distancia_haversine(0, 0, 0, 1), 111.195, places=3)
        cadastro, pontos, resumo = dados_geograficos()
        distante = {**resumo["arquivos"][0]["metadados"], "codigo": "A613", "longitude": -39.30}
        resumo["arquivos"].extend(dict(ano_arquivo=ano, metadados=distante) for ano in ANOS)
        resumo["arquivos"] = [r for r in resumo["arquivos"] if not (r["ano_arquivo"] == 2025 and r["metadados"]["codigo"] == "A612")]
        rows = gerar_vinculos(cadastro, pontos, resumo)
        self.assertEqual([r["codigo_estacao"] for r in rows], ["A612"] * 5 + ["A613"])
        self.assertEqual(rows[0]["distancia_km"], 0)
        self.assertGreater(rows[-1]["distancia_km"], 100)
        validar_vinculos(rows)

    def test_empate_tem_desempate_deterministico_por_codigo(self):
        cadastro, pontos, resumo = dados_geograficos()
        clone = {**resumo["arquivos"][0]["metadados"], "codigo": "A611"}
        resumo["arquivos"].extend(dict(ano_arquivo=ano, metadados=clone) for ano in ANOS)
        self.assertEqual({r["codigo_estacao"] for r in gerar_vinculos(cadastro, pontos, resumo)}, {"A611"})

    def test_falta_de_ponto_ou_de_estacoes_interrompe_associacao(self):
        cadastro, pontos, resumo = dados_geograficos()
        with self.assertRaisesRegex(ValueError, "correspondência"):
            gerar_vinculos(cadastro, [], resumo)
        resumo["arquivos"] = resumo["arquivos"][:-1]
        with self.assertRaisesRegex(ValueError, "Nenhuma estação"):
            gerar_vinculos(cadastro, pontos, resumo)

    def test_distancia_alterada_e_chave_repetida_sao_rejeitadas(self):
        rows = fonte_vinculos()
        with self.assertRaisesRegex(ValueError, "duplicado"):
            validar_vinculos(rows + [rows[0]])
        rows[0]["distancia_km"] = 30
        with self.assertRaisesRegex(ValueError, "Distância"):
            validar_vinculos(rows)


class InmetTests(unittest.TestCase):
    def test_fuso_separa_horas_na_transicao_de_ano(self):
        _, frame, _ = arquivo("2023/01/01;0000 UTC;1;20;50;\n2023/01/01;0300 UTC;2;22;60;\n", 2023)
        rows = agregar_horas(frame, "a" * 64)
        self.assertEqual([(r["ano"], r["semana_epidemiologica"]) for r in rows], [(2022, 52), (2023, 1)])
        self.assertEqual(rows[1]["data_inicio"], "2023-01-01")
        self.assertEqual(rows[0]["horas_observadas"], 1)

    def test_somas_e_medias_combina_arquivos_sem_media_de_medias(self):
        _, first, _ = arquivo("2020/12/31;2200 UTC;1;10;40;\n2020/12/31;2300 UTC;2;10;40;\n", 2020)
        _, second, _ = arquivo("2021/01/01;0000 UTC;3;30;70;\n", 2021)
        rows = agregar_horas(pd.concat([first, second], ignore_index=True), "a" * 64)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ano"], 2020)
        self.assertEqual(rows[0]["semana_epidemiologica"], 53)
        self.assertEqual(rows[0]["precipitacao_mm"], 6)
        self.assertAlmostEqual(rows[0]["temperatura_media_c"], 50 / 3, places=5)
        self.assertEqual(rows[0]["horas_temperatura"], 3)

    def test_ausente_permanece_nulo_e_chuva_zero_e_preservada(self):
        _, frame, metrics = arquivo("2025/01/06;0300 UTC;0;;9999;\n2025/01/06;0400 UTC;;-9999;Null;\n", 2025)
        row = agregar_horas(frame, "a" * 64)[0]
        self.assertEqual(row["precipitacao_mm"], 0)
        self.assertEqual(row["horas_precipitacao"], 1)
        self.assertIsNone(row["temperatura_media_c"])
        self.assertIsNone(row["umidade_media_pct"])
        self.assertEqual(row["horas_temperatura"], 0)
        self.assertEqual(metrics["ausentes_umidade"], 2)

    def test_medicoes_invalidas_sao_contabilizadas(self):
        _, frame, metrics = arquivo("2025/01/06;0300 UTC;-1;texto;101;\n", 2025)
        row = agregar_horas(frame, "a" * 64)[0]
        for campo in ("precipitacao_mm", "temperatura_media_c", "umidade_media_pct"):
            self.assertIsNone(row[campo])
        self.assertEqual(metrics["invalidos_precipitacao"], 1)
        self.assertEqual(metrics["invalidos_temperatura"], 1)
        self.assertEqual(metrics["invalidos_umidade"], 1)

    def test_hora_invalida_ou_duplicada_nao_e_descartada_silenciosamente(self):
        for rows in (
            "2025/01/06;2400 UTC;1;20;50;\n",
            "2025/01/06;0300 UTC;1;20;50;\n" * 2,
        ):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                arquivo(rows, 2025)
        _, frame, _ = arquivo("2025/01/06;0300 UTC;1;20;50;\n", 2025)
        with self.assertRaisesRegex(ValueError, "duplicadas"):
            agregar_horas(pd.concat([frame, frame]), "a" * 64)

    def test_cobertura_incoerente_e_chave_repetida_sao_rejeitadas(self):
        estacoes, rows = fonte_clima()
        with self.assertRaisesRegex(ValueError, "duplicada"):
            validar_clima(estacoes, rows + rows)
        rows[0]["horas_precipitacao"] = 0
        with self.assertRaisesRegex(ValueError, "cobertura"):
            validar_clima(estacoes, rows)

    def test_estacao_sem_coordenada_interrompe_validacao(self):
        estacoes, rows = fonte_clima()
        estacoes[0]["latitude"] = None
        with self.assertRaisesRegex(ValueError, "Cadastro de estação inválido"):
            validar_clima(estacoes, rows)

    def test_pacote_completo_gera_fontes_recarregaveis_e_confere_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, manifest = root / "originais.zip", root / "inventario.json"
            packages = []
            with zipfile.ZipFile(source, "w") as outer:
                for ano in ANOS:
                    inner = io.BytesIO()
                    raw = (METADATA + HEADER + f"{ano}/01/01;0000 UTC;1;20;50;\n").encode("cp1252")
                    with zipfile.ZipFile(inner, "w") as archive:
                        archive.writestr(f"INMET_SE_ES_A612_VITORIA_{ano}.CSV", raw)
                    payload = inner.getvalue()
                    outer.writestr(f"{ano}.zip", payload)
                    packages.append(dict(filename=f"{ano}.zip", source="INMET", bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(), es_weather_csv_count=1))
            manifest.write_text(json.dumps(dict(input=dict(sha256=sha256_arquivo(source)), packages=packages)), encoding="utf-8")
            original = source.read_bytes()
            processar_pacote(source, root, manifest)
            estacoes, rows = carregar_clima(root / "clima_semanal_inmet.csv", root / "clima_inmet_resumo.json", root / "estacoes_inmet.csv")
            self.assertEqual(len(estacoes), 1)
            self.assertEqual(sum(r["horas_observadas"] for r in rows), 6)
            self.assertEqual(source.read_bytes(), original)
            (root / "clima_semanal_inmet.csv").write_text("alterado", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "incompatíveis"):
                carregar_clima(root / "clima_semanal_inmet.csv", root / "clima_inmet_resumo.json", root / "estacoes_inmet.csv")


class InmetDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.directory = tempfile.TemporaryDirectory()
        self.fonte = fonte_clima()

    def tearDown(self):
        self.engine.dispose()
        self.directory.cleanup()

    def test_carga_repetida_preserva_dados_e_revisao_recebe_backup(self):
        first = sincronizar_clima(self.engine, self.fonte, backup_dir=self.directory.name)
        self.assertEqual(first["estacoes"]["inseridos"], 1)
        self.assertEqual(first["semanas"]["inseridos"], 1)
        again = sincronizar_clima(self.engine, self.fonte, backup_dir=self.directory.name)
        self.assertEqual(again["semanas"]["atualizados"], 0)
        self.assertEqual(again["semanas"]["mantidos"], 1)
        self.fonte[1][0]["precipitacao_mm"] = 3
        changed = sincronizar_clima(self.engine, self.fonte, backup_dir=self.directory.name)
        self.assertEqual(changed["semanas"]["atualizados"], 1)
        self.assertTrue(Path(changed["semanas"]["backup"]).is_file())

    def test_falha_no_clima_reverte_tambem_a_estacao(self):
        sincronizar_clima(self.engine, self.fonte, backup_dir=self.directory.name)
        self.fonte[0][0]["nome"] = "Nome atualizado"
        self.fonte[1][0]["precipitacao_mm"] = 3
        def falhar(connection, cursor, statement, parameters, context, many):
            if statement.startswith("UPDATE clima_semanal"):
                raise RuntimeError("falha simulada")
        event.listen(self.engine, "before_cursor_execute", falhar)
        try:
            with self.assertRaisesRegex(RuntimeError, "falha simulada"):
                sincronizar_clima(self.engine, self.fonte, backup_dir=self.directory.name)
        finally:
            event.remove(self.engine, "before_cursor_execute", falhar)
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(select(EstacaoMeteorologica.nome)).scalar_one(), "VITÓRIA")
            self.assertEqual(conn.execute(select(ClimaSemanal.precipitacao_mm)).scalar_one(), 2)

    def test_vinculos_exigem_cadastro_e_repeticao_nao_altera_dados(self):
        rows = fonte_vinculos()
        with self.assertRaisesRegex(ValueError, "ainda não cadastrados"):
            sincronizar_vinculos(self.engine, rows, backup_dir=self.directory.name)
        sincronizar_clima(self.engine, self.fonte, backup_dir=self.directory.name)
        with self.engine.begin() as conn:
            conn.execute(Municipio.__table__.insert(), dict(codigo_ibge="320530", nome="Vitória"))
        first = sincronizar_vinculos(self.engine, rows, backup_dir=self.directory.name)
        self.assertEqual(first["inseridos"], 6)
        again = sincronizar_vinculos(self.engine, rows, backup_dir=self.directory.name)
        self.assertEqual(again["mantidos"], 6)
        self.assertEqual(again["atualizados"], 0)
        with self.engine.begin() as conn:
            conn.execute(update(VinculoMunicipioEstacao).where(VinculoMunicipioEstacao.ano == 2020).values(observacao="legado"))
        revision = sincronizar_vinculos(self.engine, rows, backup_dir=self.directory.name)
        self.assertEqual(revision["atualizados"], 1)
        self.assertIn("legado", Path(revision["backup"]).read_text(encoding="utf-8"))

    def test_vinculos_fora_da_fonte_no_periodo_sao_preservados_e_interrompem_carga(self):
        sincronizar_clima(self.engine, self.fonte, backup_dir=self.directory.name)
        with self.engine.begin() as conn:
            conn.execute(Municipio.__table__.insert(), [dict(codigo_ibge=code, nome=code) for code in ("320530", "320520")])
        rows = fonte_vinculos()
        sincronizar_vinculos(self.engine, rows, backup_dir=self.directory.name)
        with self.engine.begin() as conn:
            extra = {**rows[0], "codigo_ibge": "320520", "codigo_ibge_completo": "3205200"}
            conn.execute(VinculoMunicipioEstacao.__table__.insert(), extra)
        with self.assertRaisesRegex(ValueError, "fora da fonte"):
            sincronizar_vinculos(self.engine, rows, backup_dir=self.directory.name)
        with self.engine.connect() as conn:
            self.assertEqual(len(conn.execute(select(VinculoMunicipioEstacao)).all()), 7)


if __name__ == "__main__":
    unittest.main()
