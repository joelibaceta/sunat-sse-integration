"""Resumen diario de boletas (``SummaryDocuments``).

En producción las boletas no se envían una a una: se informan a SUNAT en un
**resumen diario** (``sendSummary``, asíncrono → ticket → ``getStatus``). El
resumen también sirve para dar de baja boletas ya informadas (``anular``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from lxml import etree

from .documents import Boleta
from .exceptions import ValidacionError
from .models import Emisor
from .ubl import CAC, CBC, DS, EXT, _el, _money

NS_SUMMARY = "urn:sunat:names:specification:ubl:peru:schema:xsd:SummaryDocuments-1"
SAC = "urn:sunat:names:specification:ubl:peru:schema:xsd:SunatAggregateComponents-1"

# Estados del ítem en el resumen (catálogo 19).
_ESTADO_ADICIONAR = "1"
_ESTADO_ANULAR = "3"


@dataclass(kw_only=True)
class ResumenDiario:
    """Resumen diario de boletas: ``boletas`` para informar, ``anular`` para dar de baja.

    Todas las boletas del resumen deben compartir la misma fecha de emisión
    (``fecha_referencia``). ``correlativo`` distingue varios resúmenes enviados el
    mismo día.
    """

    emisor: Emisor
    boletas: list[Boleta] = field(default_factory=list)
    anular: list[Boleta] = field(default_factory=list)
    correlativo: int = 1
    fecha_generacion: date = field(default_factory=date.today)

    @property
    def fecha_referencia(self) -> date:
        return (self.boletas + self.anular)[0].fecha_emision

    @property
    def full_id(self) -> str:
        return f"RC-{self.fecha_generacion:%Y%m%d}-{self.correlativo}"

    def validar(self) -> None:
        todas = self.boletas + self.anular
        if not todas:
            raise ValidacionError("ResumenDiario: no hay boletas que informar")
        fechas = {b.fecha_emision for b in todas}
        if len(fechas) > 1:
            raise ValidacionError(
                f"ResumenDiario: todas las boletas deben tener la misma fecha de emisión (encontradas: {sorted(fechas)})"
            )
        for b in todas:
            if b.tipo != "03":
                raise ValidacionError(f"ResumenDiario: {b.full_id} no es una boleta")
            b.validar()

    def xml(self) -> bytes:
        return build_resumen_xml(self)


def _linea_resumen(parent, boleta: Boleta, idx: int, estado: str) -> None:
    _, tot = boleta.calcular()
    line = _el(parent, SAC, "SummaryDocumentsLine")
    _el(line, CBC, "LineID", idx)
    _el(line, CBC, "DocumentTypeCode", boleta.tipo)
    _el(line, CBC, "ID", boleta.full_id)

    acp = _el(line, CAC, "AccountingCustomerParty")
    _el(acp, CBC, "CustomerAssignedAccountID", boleta.cliente.numero_doc or "-")
    _el(acp, CBC, "AdditionalAccountID", boleta.cliente.tipo_doc)

    status = _el(line, CAC, "Status")
    _el(status, CBC, "ConditionCode", estado)

    _el(line, SAC, "TotalAmount", _money(tot.total), {"currencyID": boleta.moneda})

    # Importes por tipo de operación: 01 gravado, 02 exonerado, 03 inafecto.
    pagos = (("01", tot.gravado), ("02", tot.exonerado), ("03", tot.inafecto))
    for instruccion, monto in pagos:
        if monto <= 0 and instruccion != "01":
            continue
        bp = _el(line, SAC, "BillingPayment")
        _el(bp, CBC, "PaidAmount", _money(monto), {"currencyID": boleta.moneda})
        _el(bp, CBC, "InstructionID", instruccion)

    tt = _el(line, CAC, "TaxTotal")
    _el(tt, CBC, "TaxAmount", _money(tot.igv), {"currencyID": boleta.moneda})
    ts = _el(tt, CAC, "TaxSubtotal")
    _el(ts, CBC, "TaxAmount", _money(tot.igv), {"currencyID": boleta.moneda})
    tc = _el(ts, CAC, "TaxCategory")
    scheme = _el(tc, CAC, "TaxScheme")
    _el(scheme, CBC, "ID", "1000")
    _el(scheme, CBC, "Name", "IGV")
    _el(scheme, CBC, "TaxTypeCode", "VAT")


def build_resumen_xml(resumen: ResumenDiario) -> bytes:
    """Construye el XML ``SummaryDocuments`` (sin firmar) del resumen diario."""
    resumen.validar()
    ns = {None: NS_SUMMARY, "cac": CAC, "cbc": CBC, "ext": EXT, "sac": SAC, "ds": DS}
    root = etree.Element(f"{{{NS_SUMMARY}}}SummaryDocuments", nsmap=ns)

    exts = _el(root, EXT, "UBLExtensions")
    ext = _el(exts, EXT, "UBLExtension")
    _el(ext, EXT, "ExtensionContent")

    _el(root, CBC, "UBLVersionID", "2.0")
    _el(root, CBC, "CustomizationID", "1.1")
    _el(root, CBC, "ID", resumen.full_id)
    _el(root, CBC, "ReferenceDate", resumen.fecha_referencia.isoformat())
    _el(root, CBC, "IssueDate", resumen.fecha_generacion.isoformat())

    sig = _el(root, CAC, "Signature")
    _el(sig, CBC, "ID", resumen.emisor.ruc)
    sp = _el(sig, CAC, "SignatoryParty")
    spid = _el(sp, CAC, "PartyIdentification")
    _el(spid, CBC, "ID", resumen.emisor.ruc)
    spn = _el(sp, CAC, "PartyName")
    _el(spn, CBC, "Name", resumen.emisor.razon_social)
    dsa = _el(sig, CAC, "DigitalSignatureAttachment")
    er = _el(dsa, CAC, "ExternalReference")
    _el(er, CBC, "URI", "#SignatureSP")

    asp = _el(root, CAC, "AccountingSupplierParty")
    _el(asp, CBC, "CustomerAssignedAccountID", resumen.emisor.ruc)
    _el(asp, CBC, "AdditionalAccountID", "6")
    party = _el(asp, CAC, "Party")
    ple = _el(party, CAC, "PartyLegalEntity")
    _el(ple, CBC, "RegistrationName", resumen.emisor.razon_social)

    idx = 0
    for boleta in resumen.boletas:
        idx += 1
        _linea_resumen(root, boleta, idx, _ESTADO_ADICIONAR)
    for boleta in resumen.anular:
        idx += 1
        _linea_resumen(root, boleta, idx, _ESTADO_ANULAR)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=False)
