import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from pipelines.arquivos import sha256_arquivo
from scripts.pacote_modelos import conferir, exportar, restaurar


def preparar_experimentos(raiz):
    """Arquivos sintéticos: o transporte nunca precisa executar um modelo."""
    for fonte, letra in (("sesa", "a"), ("sinan", "b")):
        dataset = letra * 16
        execucao = f"20261118T031036125598Z_{dataset}"
        sufixo = "sinan" if fonte == "sinan" else ""
        modelos = raiz / "ml/models" / sufixo
        dados = raiz / "data/processed/ml" / sufixo / dataset
        rodada = modelos / execucao
        rodada.mkdir(parents=True)
        dados.mkdir(parents=True)
        (modelos / "atual.json").write_text(json.dumps({"execucao": execucao}))
        (rodada / "modelo.joblib").write_bytes(b"modelo sintetico, sem pickle")
        (dados / f"base_{fonte}.csv").write_text("municipio,registros\n320530,0\n")
        (dados / "exemplos.csv").write_text("municipio,alvo\n320530,0\n")
        resumo = dict(dataset_id=dataset, fonte=fonte,
                      base_sha256=sha256_arquivo(dados / f"base_{fonte}.csv"),
                      exemplos_sha256=sha256_arquivo(dados / "exemplos.csv"))
        (dados / "resumo.json").write_text(json.dumps(resumo))
        avaliacao = dict(**resumo, execucao=execucao, ambiente={"python": "teste"},
                         modelo_sha256=sha256_arquivo(rodada / "modelo.joblib"))
        (rodada / "avaliacao.json").write_text(json.dumps(avaliacao))
    (raiz / ".env").write_text("credencial-sintetica-nao-transportar")
    (raiz / "ml/models/antigo.joblib").write_bytes(b"fora da execucao atual")


class PacoteModelosTests(unittest.TestCase):
    def setUp(self):
        self.temporario = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporario.cleanup)
        self.raiz = Path(self.temporario.name) / "origem"
        preparar_experimentos(self.raiz)
        self.zip = Path(self.temporario.name) / "modelos.zip"
        self.manifesto = exportar(self.zip, self.raiz)
        self.hash = sha256_arquivo(self.zip)

    def test_pacote_inclui_apenas_execucoes_ativas_sem_segredos(self):
        with zipfile.ZipFile(self.zip) as pacote:
            self.assertEqual(len(pacote.namelist()), 13)
            self.assertNotIn(".env", pacote.namelist())
            self.assertNotIn("ml/models/antigo.joblib", pacote.namelist())
        self.assertEqual(conferir(self.zip, self.hash), self.manifesto)
        with self.assertRaises(FileExistsError):
            exportar(self.zip, self.raiz)

    def test_restauracao_preserva_bytes_e_pode_ser_repetida(self):
        destino = Path(self.temporario.name) / "outro-projeto"
        self.assertEqual(restaurar(self.zip, destino, self.hash), 12)
        self.assertEqual(restaurar(self.zip, destino, self.hash), 0)
        for registro in self.manifesto["arquivos"]:
            self.assertEqual(sha256_arquivo(destino / registro["caminho"]), registro["sha256"])
        self.assertFalse((destino / ".env").exists())

    def test_recusa_conflito_antes_de_restaurar_qualquer_arquivo(self):
        destino = Path(self.temporario.name) / "destino"
        existente = destino / self.manifesto["arquivos"][-1]["caminho"]
        existente.parent.mkdir(parents=True)
        existente.write_bytes(b"conteudo a preservar")
        with self.assertRaisesRegex(ValueError, "arquivo diferente"):
            restaurar(self.zip, destino, self.hash)
        self.assertEqual(existente.read_bytes(), b"conteudo a preservar")
        self.assertEqual(len([p for p in destino.rglob("*") if p.is_file()]), 1)

    def test_hash_incorreto_nao_cria_destino(self):
        destino = Path(self.temporario.name) / "nao-criar"
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            restaurar(self.zip, destino, "0" * 64)
        self.assertFalse(destino.exists())

    def test_adulteracao_de_csv_e_arquivo_inesperado_sao_rejeitados(self):
        for alteracao in ("csv", "caminho"):
            with self.subTest(alteracao=alteracao):
                adulterado = Path(self.temporario.name) / f"{alteracao}.zip"
                with zipfile.ZipFile(self.zip) as original, zipfile.ZipFile(adulterado, "w") as saida:
                    for entrada in original.infolist():
                        nome, conteudo = entrada.filename, original.read(entrada)
                        if nome.endswith("base_sesa.csv"):
                            if alteracao == "csv":
                                conteudo = conteudo.replace(b",0", b",9")
                            else:
                                nome = "../../.env"
                        saida.writestr(nome, conteudo)
                with self.assertRaises(ValueError):
                    conferir(adulterado)


if __name__ == "__main__":
    unittest.main()
