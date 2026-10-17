from datetime import date

import pytest
from lxml import etree

from sunat_see import Anulacion, ComunicacionBaja, ValidacionError
from sunat_see.baja import NS_VOIDED
from sunat_see.summary import SAC

CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"


def test_baja_estructura(emisor, factura):
    baja = ComunicacionBaja(
        emisor=emisor,
        anular=[Anulacion.de(factura, "ERROR EN DATOS DEL CLIENTE")],
        fecha_referencia=date(2026, 10, 16),
        fecha_comunicacion=date(2026, 10, 17),
        correlativo=2,
    )
    root = etree.fromstring(baja.xml())
    assert root.tag == f"{{{NS_VOIDED}}}VoidedDocuments"
    assert root.findtext(f"{{{CBC}}}ID") == "RA-20261017-2"
    assert root.findtext(f"{{{CBC}}}ReferenceDate") == "2026-10-16"
    linea = root.find(f"{{{SAC}}}VoidedDocumentsLine")
    assert linea.findtext(f"{{{CBC}}}DocumentTypeCode") == "01"
    assert linea.findtext(f"{{{SAC}}}DocumentSerialID") == "F001"
    assert linea.findtext(f"{{{SAC}}}DocumentNumberID") == "123"
    assert linea.findtext(f"{{{SAC}}}VoidReasonDescription") == "ERROR EN DATOS DEL CLIENTE"


def test_baja_no_acepta_boletas():
    with pytest.raises(ValidacionError, match="ResumenDiario"):
        Anulacion("03", "B001", 1)


def test_baja_vacia_falla(emisor):
    baja = ComunicacionBaja(emisor=emisor, anular=[], fecha_referencia=date(2026, 10, 16))
    with pytest.raises(ValidacionError, match="no hay comprobantes"):
        baja.validar()


def test_baja_fechas_coherentes(emisor, factura):
    baja = ComunicacionBaja(
        emisor=emisor,
        anular=[Anulacion.de(factura)],
        fecha_referencia=date(2026, 10, 16),
        fecha_comunicacion=date(2026, 10, 10),
    )
    with pytest.raises(ValidacionError, match="anterior a la de emisión"):
        baja.validar()


def test_anulacion_motivo_obligatorio():
    with pytest.raises(ValidacionError, match="motivo"):
        Anulacion("01", "F001", 1, motivo="  ")
