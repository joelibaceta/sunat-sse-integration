from datetime import date

import pytest
from lxml import etree

from sunat_see import Boleta, Cliente, Item, ResumenDiario, ValidacionError
from sunat_see.summary import SAC

CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"


def test_resumen_diario_estructura(emisor, boleta):
    otra = Boleta(
        serie="B001", numero=46, emisor=emisor,
        cliente=Cliente.publico_general(),
        fecha_emision=date(2026, 10, 16),
        items=[Item("Gaseosa", 2, precio="3.50")],
    )
    resumen = ResumenDiario(
        emisor=emisor,
        boletas=[boleta, otra],
        fecha_generacion=date(2026, 10, 17),
        correlativo=1,
    )
    root = etree.fromstring(resumen.xml())
    assert root.findtext(f"{{{CBC}}}ID") == "RC-20261017-1"
    assert root.findtext(f"{{{CBC}}}ReferenceDate") == "2026-10-16"
    assert root.findtext(f"{{{CBC}}}IssueDate") == "2026-10-17"
    lineas = root.findall(f"{{{SAC}}}SummaryDocumentsLine")
    assert len(lineas) == 2
    assert lineas[0].findtext(f"{{{CBC}}}ID") == "B001-45"
    assert lineas[0].findtext(f"{{{CAC}}}Status/{{{CBC}}}ConditionCode") == "1"


def test_resumen_anular_usa_estado_3(emisor, boleta):
    resumen = ResumenDiario(emisor=emisor, anular=[boleta], fecha_generacion=date(2026, 10, 17))
    root = etree.fromstring(resumen.xml())
    linea = root.find(f"{{{SAC}}}SummaryDocumentsLine")
    assert linea.findtext(f"{{{CAC}}}Status/{{{CBC}}}ConditionCode") == "3"


def test_resumen_exige_misma_fecha(emisor, boleta):
    otra = Boleta(
        serie="B001", numero=46, emisor=emisor,
        cliente=Cliente.publico_general(),
        fecha_emision=date(2026, 10, 15),
        items=[Item("Gaseosa", 1, precio="3.50")],
    )
    resumen = ResumenDiario(emisor=emisor, boletas=[boleta, otra])
    with pytest.raises(ValidacionError, match="misma fecha"):
        resumen.validar()


def test_resumen_vacio_falla(emisor):
    with pytest.raises(ValidacionError, match="no hay boletas"):
        ResumenDiario(emisor=emisor).validar()
