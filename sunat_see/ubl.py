"""Construcción del XML UBL 2.1 (sin firmar) de facturas, boletas y notas.

Puro y sin efectos: recibe un comprobante declarativo y devuelve ``bytes``.
La firma XAdES-BES se inserta después en ``ext:ExtensionContent`` (``signer.py``).

Catálogos: 01 (tipo de comprobante), 05 (tributos), 06 (doc. identidad),
07 (afectación IGV), 09/10 (motivo de notas), 16 (tipo de precio), 51 (operación).
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from lxml import etree

from .catalogs import Afectacion
from .documents import Boleta, Factura, LineaCalculada, NotaCredito, NotaDebito, Totales, _Comprobante
from .letras import monto_en_letras
from .models import Credito

CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
EXT = "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
DS = "http://www.w3.org/2000/09/xmldsig#"

_NS_ROOT = {
    "01": ("urn:oasis:names:specification:ubl:schema:xsd:Invoice-2", "Invoice"),
    "03": ("urn:oasis:names:specification:ubl:schema:xsd:Invoice-2", "Invoice"),
    "07": ("urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2", "CreditNote"),
    "08": ("urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2", "DebitNote"),
}

# Afectación → (código de tributo cat. 05, nombre, código internacional)
_ESQUEMA_TRIBUTO = {
    Afectacion.GRAVADO: ("1000", "IGV", "VAT"),
    Afectacion.EXONERADO: ("9997", "EXO", "VAT"),
    Afectacion.INAFECTO: ("9998", "INA", "FRE"),
    Afectacion.EXPORTACION: ("9995", "EXP", "FRE"),
}

_CAT06_ATTRS = {
    "schemeName": "Documento de Identidad",
    "schemeAgencyName": "PE:SUNAT",
    "schemeURI": "urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo06",
}


def _money(v: Decimal) -> str:
    """Importe a 2 decimales fijos (HALF_UP), como exige SUNAT."""
    return str(Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _plain(v: Decimal, decimales: int) -> str:
    """Número en notación plana (sin exponente), hasta ``decimales``, sin ceros finales."""
    d = Decimal(v).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def _el(parent, ns, tag, text=None, attrib=None):
    el = etree.SubElement(parent, f"{{{ns}}}{tag}")
    if text is not None:
        el.text = str(text)
    if attrib:
        for k, v in attrib.items():
            el.set(k, str(v))
    return el


def build_xml(doc: _Comprobante) -> bytes:
    """Valida el comprobante y construye su XML UBL 2.1 sin firmar."""
    doc.validar()
    if doc.tipo in ("01", "03"):
        return _invoice(doc)
    if doc.tipo == "07":
        return _nota(doc, es_credito=True)
    if doc.tipo == "08":
        return _nota(doc, es_credito=False)
    raise ValueError(f"Tipo de comprobante no soportado: {doc.tipo}")


# --- Bloques comunes ----------------------------------------------------------


def _root(doc) -> etree._Element:
    uri, tag = _NS_ROOT[doc.tipo]
    ns = {None: uri, "cac": CAC, "cbc": CBC, "ext": EXT, "ds": DS}
    root = etree.Element(f"{{{uri}}}{tag}", nsmap=ns)
    # Placeholder donde signer.py insertará la firma (exigencia de SUNAT).
    exts = _el(root, EXT, "UBLExtensions")
    ext = _el(exts, EXT, "UBLExtension")
    _el(ext, EXT, "ExtensionContent")
    _el(root, CBC, "UBLVersionID", "2.1")
    _el(root, CBC, "CustomizationID", "2.0")
    _el(root, CBC, "ID", doc.full_id)
    _el(root, CBC, "IssueDate", doc.fecha_emision.isoformat())
    return root


def _leyendas(root, doc, totales: Totales) -> None:
    # Leyenda 1000: monto en letras (obligatoria en la representación impresa).
    _el(root, CBC, "Note", monto_en_letras(totales.total, doc.moneda), {"languageLocaleID": "1000"})
    for nota in doc.observaciones:
        _el(root, CBC, "Note", nota)


def _firma_ref(root, doc) -> None:
    """Bloque ``cac:Signature`` que referencia la firma de ``ExtensionContent``."""
    sig = _el(root, CAC, "Signature")
    _el(sig, CBC, "ID", doc.emisor.ruc)
    sp = _el(sig, CAC, "SignatoryParty")
    spid = _el(sp, CAC, "PartyIdentification")
    _el(spid, CBC, "ID", doc.emisor.ruc)
    spn = _el(sp, CAC, "PartyName")
    _el(spn, CBC, "Name", doc.emisor.razon_social)
    dsa = _el(sig, CAC, "DigitalSignatureAttachment")
    er = _el(dsa, CAC, "ExternalReference")
    _el(er, CBC, "URI", "#SignatureSP")


def _supplier(root, doc) -> None:
    e = doc.emisor
    asp = _el(root, CAC, "AccountingSupplierParty")
    party = _el(asp, CAC, "Party")
    pid = _el(party, CAC, "PartyIdentification")
    _el(pid, CBC, "ID", e.ruc, {"schemeID": "6", **_CAT06_ATTRS})
    if e.nombre_comercial:
        pn = _el(party, CAC, "PartyName")
        _el(pn, CBC, "Name", e.nombre_comercial)
    ple = _el(party, CAC, "PartyLegalEntity")
    _el(ple, CBC, "RegistrationName", e.razon_social)
    addr = _el(ple, CAC, "RegistrationAddress")
    if e.ubigeo:
        _el(addr, CBC, "ID", e.ubigeo)
    _el(addr, CBC, "AddressTypeCode", e.codigo_local or "0000")
    line = _el(addr, CAC, "AddressLine")
    _el(line, CBC, "Line", e.direccion or "-")


def _customer(root, doc) -> None:
    c = doc.cliente
    acp = _el(root, CAC, "AccountingCustomerParty")
    party = _el(acp, CAC, "Party")
    pid = _el(party, CAC, "PartyIdentification")
    _el(pid, CBC, "ID", c.numero_doc or "-", {"schemeID": c.tipo_doc, **_CAT06_ATTRS})
    ple = _el(party, CAC, "PartyLegalEntity")
    _el(ple, CBC, "RegistrationName", c.nombre or "-")
    if c.direccion:
        addr = _el(ple, CAC, "RegistrationAddress")
        line = _el(addr, CAC, "AddressLine")
        _el(line, CBC, "Line", c.direccion)


def _forma_pago(root, doc: Factura, totales: Totales) -> None:
    fp = doc.forma_pago
    pt = _el(root, CAC, "PaymentTerms")
    _el(pt, CBC, "ID", "FormaPago")
    if not isinstance(fp, Credito):
        _el(pt, CBC, "PaymentMeansID", "Contado")
        return
    _el(pt, CBC, "PaymentMeansID", "Credito")
    _el(pt, CBC, "Amount", _money(totales.total), {"currencyID": doc.moneda})
    for i, cuota in enumerate(fp.cuotas, start=1):
        ptc = _el(root, CAC, "PaymentTerms")
        _el(ptc, CBC, "ID", "FormaPago")
        _el(ptc, CBC, "PaymentMeansID", f"Cuota{i:03d}")
        _el(ptc, CBC, "Amount", _money(cuota.monto), {"currencyID": doc.moneda})
        _el(ptc, CBC, "PaymentDueDate", cuota.vencimiento.isoformat())


def _tax_category(parent, afectacion: Afectacion, tasa_igv: Decimal) -> None:
    codigo, nombre, tipo = _ESQUEMA_TRIBUTO[afectacion]
    pct = tasa_igv * 100 if afectacion is Afectacion.GRAVADO else Decimal("0")
    tc = _el(parent, CAC, "TaxCategory")
    _el(tc, CBC, "Percent", _money(pct))
    _el(tc, CBC, "TaxExemptionReasonCode", afectacion.value, {
        "listAgencyName": "PE:SUNAT",
        "listName": "Afectacion del IGV",
        "listURI": "urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo07",
    })
    scheme = _el(tc, CAC, "TaxScheme")
    _el(scheme, CBC, "ID", codigo, {
        "schemeName": "Codigo de tributos",
        "schemeAgencyName": "PE:SUNAT",
        "schemeURI": "urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo05",
    })
    _el(scheme, CBC, "Name", nombre)
    _el(scheme, CBC, "TaxTypeCode", tipo)


def _tax_total_doc(root, doc, totales: Totales) -> None:
    tt = _el(root, CAC, "TaxTotal")
    _el(tt, CBC, "TaxAmount", _money(totales.igv), {"currencyID": doc.moneda})
    bases = (
        (Afectacion.GRAVADO, totales.gravado, totales.igv),
        (Afectacion.EXONERADO, totales.exonerado, Decimal("0")),
        (Afectacion.INAFECTO, totales.inafecto, Decimal("0")),
        (Afectacion.EXPORTACION, totales.exportacion, Decimal("0")),
    )
    for afectacion, base, igv in bases:
        if base <= 0 and afectacion is not Afectacion.GRAVADO:
            continue
        ts = _el(tt, CAC, "TaxSubtotal")
        _el(ts, CBC, "TaxableAmount", _money(base), {"currencyID": doc.moneda})
        _el(ts, CBC, "TaxAmount", _money(igv), {"currencyID": doc.moneda})
        _tax_category(ts, afectacion, doc.igv)


def _monetary_total(root, doc, totales: Totales, tag: str) -> None:
    lmt = _el(root, CAC, tag)
    _el(lmt, CBC, "LineExtensionAmount", _money(totales.subtotal), {"currencyID": doc.moneda})
    _el(lmt, CBC, "TaxInclusiveAmount", _money(totales.total), {"currencyID": doc.moneda})
    _el(lmt, CBC, "PayableAmount", _money(totales.total), {"currencyID": doc.moneda})


def _linea(doc, lc: LineaCalculada, idx: int, line_tag: str, qty_tag: str) -> etree._Element:
    item = lc.item
    il = etree.Element(f"{{{CAC}}}{line_tag}")
    _el(il, CBC, "ID", idx)
    _el(il, CBC, qty_tag, _plain(item.cantidad, 10), {"unitCode": item.unidad})
    _el(il, CBC, "LineExtensionAmount", _money(lc.valor_venta), {"currencyID": doc.moneda})

    # Precio de venta unitario con IGV como referencia (catálogo 16: 01).
    pr = _el(il, CAC, "PricingReference")
    acp = _el(pr, CAC, "AlternativeConditionPrice")
    _el(acp, CBC, "PriceAmount", _plain(lc.precio_unitario, 10), {"currencyID": doc.moneda})
    _el(acp, CBC, "PriceTypeCode", "01")

    tt = _el(il, CAC, "TaxTotal")
    _el(tt, CBC, "TaxAmount", _money(lc.igv), {"currencyID": doc.moneda})
    ts = _el(tt, CAC, "TaxSubtotal")
    _el(ts, CBC, "TaxableAmount", _money(lc.valor_venta), {"currencyID": doc.moneda})
    _el(ts, CBC, "TaxAmount", _money(lc.igv), {"currencyID": doc.moneda})
    _tax_category(ts, item.afectacion, doc.igv)

    it = _el(il, CAC, "Item")
    _el(it, CBC, "Description", item.descripcion)
    if item.codigo:
        sii = _el(it, CAC, "SellersItemIdentification")
        _el(sii, CBC, "ID", item.codigo)
    price = _el(il, CAC, "Price")
    _el(price, CBC, "PriceAmount", _plain(lc.valor_unitario, 10), {"currencyID": doc.moneda})
    return il


# --- Factura / Boleta ---------------------------------------------------------


def _invoice(doc: Factura | Boleta) -> bytes:
    lineas, totales = doc.calcular()
    root = _root(doc)
    if isinstance(doc, Factura) and doc.fecha_vencimiento:
        _el(root, CBC, "DueDate", doc.fecha_vencimiento.isoformat())
    _el(root, CBC, "InvoiceTypeCode", doc.tipo, {
        "listID": doc.operacion,
        "listAgencyName": "PE:SUNAT",
        "listName": "Tipo de Documento",
        "listURI": "urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo01",
    })
    _leyendas(root, doc, totales)
    _el(root, CBC, "DocumentCurrencyCode", doc.moneda)
    _firma_ref(root, doc)
    _supplier(root, doc)
    _customer(root, doc)
    if isinstance(doc, Factura):
        _forma_pago(root, doc, totales)
    _tax_total_doc(root, doc, totales)
    _monetary_total(root, doc, totales, "LegalMonetaryTotal")
    for idx, lc in enumerate(lineas, start=1):
        root.append(_linea(doc, lc, idx, "InvoiceLine", "InvoicedQuantity"))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=False)


# --- Notas de crédito / débito -------------------------------------------------


def _nota(doc: NotaCredito | NotaDebito, es_credito: bool) -> bytes:
    lineas, totales = doc.calcular()
    ref = doc.referencia
    root = _root(doc)
    _leyendas(root, doc, totales)
    _el(root, CBC, "DocumentCurrencyCode", doc.moneda)

    dr = _el(root, CAC, "DiscrepancyResponse")
    _el(dr, CBC, "ReferenceID", ref.full_id)
    _el(dr, CBC, "ResponseCode", doc.motivo.value)
    _el(dr, CBC, "Description", doc.sustento)

    br = _el(root, CAC, "BillingReference")
    idr = _el(br, CAC, "InvoiceDocumentReference")
    _el(idr, CBC, "ID", ref.full_id)
    _el(idr, CBC, "DocumentTypeCode", ref.tipo)

    _firma_ref(root, doc)
    _supplier(root, doc)
    _customer(root, doc)
    _tax_total_doc(root, doc, totales)
    _monetary_total(root, doc, totales, "LegalMonetaryTotal" if es_credito else "RequestedMonetaryTotal")
    line_tag, qty_tag = ("CreditNoteLine", "CreditedQuantity") if es_credito else ("DebitNoteLine", "DebitedQuantity")
    for idx, lc in enumerate(lineas, start=1):
        root.append(_linea(doc, lc, idx, line_tag, qty_tag))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=False)
