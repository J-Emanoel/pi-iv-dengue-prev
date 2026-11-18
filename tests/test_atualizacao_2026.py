import contextlib
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from sqlalchemy import create_engine, event, select

from backend.database import Base
from backend.models import CasoDengue, Municipio, NotificacaoEstadual
from backend.povoar_banco import FonteCarga, carregar_fonte, sincronizar_atualizacao_2026
from pipelines.arquivos import conferir_atualizacao_2026, sha256_arquivo
from pipelines.etl_inmet import ANOS, ANOS_SUPORTADOS, agregar_horas, carregar_clima, processar_pacote as processar_clima
from pipelines.etl_sinan import processar_pacote as processar_sinan
from pipelines.vincular_estacoes import gerar_vinculos
from tests.test_etl_sinan import HEADER as HEADER_SINAN
from tests.test_inmet import HEADER, METADATA, arquivo, dados_geograficos


class AtualizacaoEtlTests(unittest.TestCase):
    def test_sinan_anual_2026_filtra_residencia_e_preserva_semana_e_ausencia(self):
        with tempfile.TemporaryDirectory() as folder:
            pasta = Path(folder)
            entrada = pasta / 'DENGBR26.csv.zip'
            with zipfile.ZipFile(entrada, 'w') as z:
                z.writestr('DENGBR26.csv', HEADER_SINAN +
                           '32,320530,2026-10-31,2026-11-02,202643,31,10\n' +
                           '31,310620,2026-10-31,2026-11-02,202643,32,10\n')
            original = entrada.read_bytes()
            with contextlib.redirect_stdout(io.StringIO()):
                resumo = processar_sinan(entrada, [2026], pasta/'saida.csv', pasta/'saida.json', chunksize=1)
            fonte = carregar_fonte(pasta/'saida.csv', pasta/'saida.json')
            self.assertEqual(resumo['formato_entrada'], 'zip_anual')
            self.assertEqual(resumo['contadores']['linhas_bruto'], 2)
            self.assertEqual(fonte.registros, [dict(codigo_ibge='320530', ano=2026, semana_epidemiologica=43, quantidade_casos=1)])
            self.assertEqual(original, entrada.read_bytes())
            with self.assertRaisesRegex(ValueError, 'único ano'):
                processar_sinan(entrada, [2025,2026], pasta/'saida.csv', pasta/'saida.json')
            self.assertEqual(carregar_fonte(pasta/'saida.csv', pasta/'saida.json').registros, fonte.registros)

    def test_inmet_2026_combina_borda_do_ano_e_ignora_outros_estados(self):
        with tempfile.TemporaryDirectory() as folder:
            pasta = Path(folder)
            entrada, novo = pasta/'original.zip', pasta/'2026.zip'
            pacotes = []
            with zipfile.ZipFile(entrada,'w') as outer:
                for ano in ANOS:
                    bloco = io.BytesIO()
                    linha = f'{ano}/12/31;2300 UTC;1;20;50;\n' if ano==2025 else f'{ano}/01/06;0300 UTC;1;20;50;\n'
                    with zipfile.ZipFile(bloco,'w') as z:
                        z.writestr(f'INMET_SE_ES_A612_VITORIA_{ano}.CSV',(METADATA+HEADER+linha).encode('cp1252'))
                    outer.writestr(f'{ano}.zip',bloco.getvalue())
                    pacotes.append(dict(filename=f'{ano}.zip',source='INMET',bytes=len(bloco.getvalue()),
                                        sha256=hashlib.sha256(bloco.getvalue()).hexdigest(),es_weather_csv_count=1))
            with zipfile.ZipFile(novo,'w') as z:
                z.writestr('INMET_SE_ES_A612_VITORIA_2026.CSV',(METADATA+HEADER+
                           '2026/01/01;0000 UTC;2;30;70;\n2026/01/04;0300 UTC;0;22;60;\n').encode('cp1252'))
                z.writestr('INMET_SE_SP_A999_OUTRO_2026.CSV','não deve ser interpretado')
            manifesto = pasta/'manifesto.json'
            manifesto.write_text(json.dumps(dict(input=dict(sha256=sha256_arquivo(entrada)),packages=pacotes)),encoding='utf-8')
            revisao = pasta/'revisao.json'
            revisao.write_text(json.dumps(dict(inmet=dict(bytes=novo.stat().st_size,sha256=sha256_arquivo(novo)))),encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                resumo = processar_clima(entrada,pasta,manifesto,atualizacao_2026=novo,manifesto_atualizacao=revisao)
            estacoes, semanas = carregar_clima(pasta/'clima_semanal_inmet.csv',pasta/'clima_inmet_resumo.json',pasta/'estacoes_inmet.csv')
            self.assertEqual(resumo['anos_arquivos'],ANOS_SUPORTADOS)
            self.assertEqual(len(estacoes),1)
            borda = next(r for r in semanas if (r['ano'],r['semana_epidemiologica'])==(2025,53))
            self.assertEqual(borda['horas_observadas'],2)
            self.assertEqual(borda['precipitacao_mm'],3)
            self.assertEqual(borda['temperatura_media_c'],25)
            self.assertEqual(next(r for r in semanas if r['ano']==2026)['precipitacao_mm'],0)
            cadastro,pontos,_=dados_geograficos()
            vinculos=gerar_vinculos(cadastro,pontos,resumo)
            self.assertEqual([r['ano'] for r in vinculos],ANOS_SUPORTADOS)
            with novo.open('ab') as stream:
                stream.write(b'alterado')
            with self.assertRaisesRegex(ValueError,'versão conferida'):
                conferir_atualizacao_2026(novo,'inmet',revisao)


class AtualizacaoDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.temporary=tempfile.TemporaryDirectory()
        with self.engine.begin() as conn:
            conn.execute(Municipio.__table__.insert(),dict(codigo_ibge='320530',nome='Vitória'))
            conn.execute(CasoDengue.__table__.insert(),[
                dict(codigo_ibge='320530',ano=2025,semana_epidemiologica=1,quantidade_casos=7),
                dict(codigo_ibge='320530',ano=2026,semana_epidemiologica=1,quantidade_casos=99)])
            conn.execute(NotificacaoEstadual.__table__.insert(),dict(codigo_ibge='320530',ano=2024,
                semana_epidemiologica=1,registros_notificados=123,data_referencia='DATA_NOTIFICACAO',
                fonte_url='https://exemplo.invalid',fonte_manifesto_sha256='a'*64,fonte_csv_sha256='b'*64))
        estacao,horas,_=arquivo('2026/01/04;0300 UTC;0;20;50;\n',2026)
        estacao['fonte_sha256']='a'*64
        self.clima=([estacao],agregar_horas(horas,'a'*64))
        cadastro,pontos,_=dados_geograficos()
        resumo=dict(entrada_sha256='a'*64,anos_arquivos=ANOS_SUPORTADOS,
                    arquivos=[dict(ano_arquivo=ano,metadados=estacao) for ano in ANOS_SUPORTADOS])
        self.vinculos=gerar_vinculos(cadastro,pontos,resumo)
        self.fonte=FonteCarga([dict(codigo_ibge='320530',ano=2026,semana_epidemiologica=1,quantidade_casos=1)],[2026])

    def tearDown(self):
        self.engine.dispose()
        self.temporary.cleanup()

    def snapshot(self):
        with self.engine.connect() as conn:
            return {t.name:[tuple(r) for r in conn.execute(select(t))] for t in Base.metadata.sorted_tables}

    def test_atualizacao_preserva_sesa_outros_anos_e_repeticao_nao_altera_dados(self):
        resultado=sincronizar_atualizacao_2026(self.engine,self.fonte,self.clima,self.vinculos,backup_dir=self.temporary.name)
        self.assertEqual(resultado['sinan']['atualizados'],1)
        self.assertTrue(Path(resultado['sinan']['backup']).is_file())
        antes=self.snapshot()
        repetida=sincronizar_atualizacao_2026(self.engine,self.fonte,self.clima,self.vinculos,backup_dir=self.temporary.name)
        self.assertEqual(self.snapshot(),antes)
        self.assertEqual(repetida['sinan']['atualizados'],0)
        self.assertEqual(repetida['clima']['semanas']['inseridos'],0)
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(select(CasoDengue.quantidade_casos).where(CasoDengue.ano==2025)).scalar_one(),7)
            self.assertEqual(conn.execute(select(NotificacaoEstadual.registros_notificados)).scalar_one(),123)

    def test_falha_nos_vinculos_reverte_tambem_casos_e_clima(self):
        antes=self.snapshot()
        def falhar(conn,cursor,statement,parameters,context,many):
            if statement.startswith('INSERT INTO municipios_estacoes'):
                raise RuntimeError('falha simulada no último componente')
        event.listen(self.engine,'before_cursor_execute',falhar)
        try:
            with self.assertRaisesRegex(RuntimeError,'falha simulada'):
                sincronizar_atualizacao_2026(self.engine,self.fonte,self.clima,self.vinculos,backup_dir=self.temporary.name)
        finally:
            event.remove(self.engine,'before_cursor_execute',falhar)
        self.assertEqual(self.snapshot(),antes)


if __name__=='__main__':
    unittest.main()
