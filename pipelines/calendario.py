"""Semana epidemiológica: domingo a sábado, primeira semana com >= 4 dias."""

from datetime import date, timedelta


def inicio_ano_epidemiologico(ano: int) -> date:
    janeiro_quatro = date(ano, 1, 4)
    return janeiro_quatro - timedelta(days=(janeiro_quatro.weekday() + 1) % 7)


def ano_semana_epidemiologica(dia: date) -> tuple[int, int]:
    domingo = dia - timedelta(days=(dia.weekday() + 1) % 7)
    ano = (domingo + timedelta(days=3)).year
    semana = (domingo - inicio_ano_epidemiologico(ano)).days // 7 + 1
    return ano, semana


def semanas_no_ano(ano: int) -> int:
    return (inicio_ano_epidemiologico(ano + 1) - inicio_ano_epidemiologico(ano)).days // 7
