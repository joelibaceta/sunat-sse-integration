"""Comunicación de Baja (anulación) de facturas y notas — ``VoidedDocuments``.

Anula comprobantes **ya aceptados** por SUNAT, dentro del plazo legal (7 días
de la emisión). Se envía por ``sendSummary`` (asíncrono → ticket) y el CDR de la
baja se recupera con ``getStatus``.

Las **boletas** no se anulan por esta vía: se dan de baja en el resumen diario
(``ResumenDiario(anular=[...])``).

Nombre del archivo: ``<RUC>-RA-<YYYYMMDD>-<correlativo>``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from lxml import etree

from .documents import _Comprobante
from .exceptions import ValidacionError
from .models import Emisor
from .summary import SAC
from .ubl import CAC, CBC, DS, EXT, _el

NS_VOIDED = "urn:sunat:names:specification:ubl:peru:schema:xsd:VoidedDocuments-1"

# Tipos anulables por RA. Las boletas (03) van por el resumen diario.
_TIPOS_ANULABLES = {"01", "07", "08"}


@dataclass(frozen=True)
class Anulacion:
    """Un comprobante a anular. Usa ``Anulacion.de(factura, motivo)`` si tienes el objeto."""

    tipo: str
    serie: str
    numero: int
    motivo: str = "ANULACION DE LA OPERACION"

    def __post_init__(self):
        if self.tipo not in _TIPOS_ANULABLES:
            extra = " (las boletas se anulan con ResumenDiario(anular=[...]))" if self.tipo == "03" else ""
            raise ValidacionError(f"Anulacion: tipo '{self.tipo}' no anulable por Comunicación de Baja{extra}")
        if not self.motivo.strip():
            raise ValidacionError("Anulacion: el motivo no puede estar vacío")

    @classmethod
    def de(cls, documento: _Comprobante, motivo: str = "ANULACION DE LA OPERACION") -> "Anulacion":
        return cls(documento.tipo, documento.serie, int(documento.numero), motivo)


@dataclass(kw_only=True)
class ComunicacionBaja:
    """Comunicación de Baja (RA): anula facturas/notas de UNA misma fecha de emisión.

    ``fecha_referencia`` es la fecha de emisión de los comprobantes a anular;
    ``correlativo`` distingue varias comunicaciones enviadas el mismo día.
    """

    emisor: Emisor
    anular: list[Anulacion]
    fecha_referencia: date
    fecha_comunicacion: date = field(default_factory=date.today)
    correlativo: int = 1

    @property
    def full_id(self) -> str:
        return f"RA-{self.fecha_comunicacion:%Y%m%d}-{self.correlativo}"

    def validar(self) -> None:
        if not self.anular:
            raise ValidacionError("ComunicacionBaja: no hay comprobantes que anular")
        if self.fecha_comunicacion < self.fecha_referencia:
            raise ValidacionError(
                "ComunicacionBaja: la fecha de comunicación no puede ser anterior a la de emisión"
            )

    def xml(self) -> bytes:
        return build_baja_xml(self)


def build_baja_xml(baja: ComunicacionBaja) -> bytes:
    """Construye el XML ``VoidedDocuments`` (sin firmar) de la comunicación de baja."""
    baja.validar()
    ns = {None: NS_VOIDED, "cac": CAC, "cbc": CBC, "ext": EXT, "sac": SAC, "ds": DS}
    root = etree.Element(f"{{{NS_VOIDED}}}VoidedDocuments", nsmap=ns)

    exts = _el(root, EXT, "UBLExtensions")
    ext = _el(exts, EXT, "UBLExtension")
    _el(ext, EXT, "ExtensionContent")

    _el(root, CBC, "UBLVersionID", "2.0")
    _el(root, CBC, "CustomizationID", "1.0")
    _el(root, CBC, "ID", baja.full_id)
    _el(root, CBC, "ReferenceDate", baja.fecha_referencia.isoformat())
    _el(root, CBC, "IssueDate", baja.fecha_comunicacion.isoformat())

    sig = _el(root, CAC, "Signature")
    _el(sig, CBC, "ID", baja.emisor.ruc)
    sp = _el(sig, CAC, "SignatoryParty")
    spid = _el(sp, CAC, "PartyIdentification")
    _el(spid, CBC, "ID", baja.emisor.ruc)
    spn = _el(sp, CAC, "PartyName")
    _el(spn, CBC, "Name", baja.emisor.razon_social)
    dsa = _el(sig, CAC, "DigitalSignatureAttachment")
    er = _el(dsa, CAC, "ExternalReference")
    _el(er, CBC, "URI", "#SignatureSP")

    asp = _el(root, CAC, "AccountingSupplierParty")
    _el(asp, CBC, "CustomerAssignedAccountID", baja.emisor.ruc)
    _el(asp, CBC, "AdditionalAccountID", "6")
    party = _el(asp, CAC, "Party")
    ple = _el(party, CAC, "PartyLegalEntity")
    _el(ple, CBC, "RegistrationName", baja.emisor.razon_social)

    for i, item in enumerate(baja.anular, start=1):
        line = _el(root, SAC, "VoidedDocumentsLine")
        _el(line, CBC, "LineID", i)
        _el(line, CBC, "DocumentTypeCode", item.tipo)
        _el(line, SAC, "DocumentSerialID", item.serie)
        _el(line, SAC, "DocumentNumberID", item.numero)
        _el(line, SAC, "VoidReasonDescription", item.motivo)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=False)
