from decimal import Decimal

import pytest

from sunat_see.letras import monto_en_letras, numero_a_letras


@pytest.mark.parametrize(
    ("numero", "esperado"),
    [
        (0, "CERO"),
        (1, "UNO"),
        (15, "QUINCE"),
        (16, "DIECISEIS"),
        (21, "VEINTIUNO"),
        (30, "TREINTA"),
        (99, "NOVENTA Y NUEVE"),
        (100, "CIEN"),
        (101, "CIENTO UNO"),
        (500, "QUINIENTOS"),
        (999, "NOVECIENTOS NOVENTA Y NUEVE"),
        (1000, "MIL"),
        (1419, "MIL CUATROCIENTOS DIECINUEVE"),
        (21000, "VEINTIUN MIL"),
        (100000, "CIEN MIL"),
        (1000000, "UN MILLON"),
        (2500000, "DOS MILLONES QUINIENTOS MIL"),
    ],
)
def test_numero_a_letras(numero, esperado):
    assert numero_a_letras(numero) == esperado


def test_monto_en_letras_soles():
    assert monto_en_letras(Decimal("1419.00")) == "MIL CUATROCIENTOS DIECINUEVE CON 00/100 SOLES"


def test_monto_en_letras_con_centimos():
    assert monto_en_letras(Decimal("15.50")) == "QUINCE CON 50/100 SOLES"


def test_monto_en_letras_dolares():
    assert monto_en_letras(Decimal("100.00"), "USD") == "CIEN CON 00/100 DOLARES AMERICANOS"
