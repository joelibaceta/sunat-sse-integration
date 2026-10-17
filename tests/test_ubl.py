from datetime import date
from decimal import Decimal

from lxml import etree

from sunat_see import Credito, Cuota, NotaCredito, NotaDebito, Item

CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
EXT = "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"


def _parse(doc):
    return etree.fromstring(doc.xml())


def _textos(root, path):
    return [e.text for e in root.findall(path)]


def test_factura_estructura_basica(factura):
    root = _parse(factura)
    assert root.tag.endswith("}Invoice")
    assert root.findtext(f"{{{CBC}}}ID") == "F001-123"
    assert root.findtext(f"{{{CBC}}}IssueDate") == "2026-10-16"
    tipo = root.find(f"{{{CBC}}}InvoiceTypeCode")
    assert tipo.text == "01"
    assert tipo.get("listID") == "0101"
    # Placeholder para la firma
    assert root.find(f"{{{EXT}}}UBLExtensions/{{{EXT}}}UBLExtension/{{{EXT}}}ExtensionContent") is not None
    # Leyenda monto en letras
    nota = root.find(f"{{{CBC}}}Note")
    assert nota.get("languageLocaleID") == "1000"
    assert "CON 00/100 SOLES" in nota.text


def test_factura_contado_por_defecto(factura):
    root = _parse(factura)
    medios = _textos(root, f"{{{CAC}}}PaymentTerms/{{{CBC}}}PaymentMeansID")
    assert medios == ["Contado"]


def test_factura_al_credito_emite_cuotas(factura):
    factura.forma_pago = Credito([
        Cuota(monto=Decimal("1000.00"), vencimiento=date(2026, 11, 15)),
        Cuota(monto=Decimal("1419.00"), vencimiento=date(2026, 12, 15)),
    ])
    root = _parse(factura)
    medios = _textos(root, f"{{{CAC}}}PaymentTerms/{{{CBC}}}PaymentMeansID")
    assert medios == ["Credito", "Cuota001", "Cuota002"]
    vencimientos = _textos(root, f"{{{CAC}}}PaymentTerms/{{{CBC}}}PaymentDueDate")
    assert vencimientos == ["2026-11-15", "2026-12-15"]


def test_factura_totales_en_xml(factura):
    root = _parse(factura)
    lmt = root.find(f"{{{CAC}}}LegalMonetaryTotal")
    assert lmt.findtext(f"{{{CBC}}}LineExtensionAmount") == "2050.00"
    assert lmt.findtext(f"{{{CBC}}}PayableAmount") == "2419.00"
    tax = root.find(f"{{{CAC}}}TaxTotal/{{{CBC}}}TaxAmount")
    assert tax.text == "369.00"
    lineas = root.findall(f"{{{CAC}}}InvoiceLine")
    assert len(lineas) == 2
    assert lineas[0].findtext(f"{{{CBC}}}InvoicedQuantity") == "2"


def test_boleta_estructura(boleta):
    root = _parse(boleta)
    assert root.findtext(f"{{{CBC}}}InvoiceTypeCode") == "03"
    assert root.findtext(f"{{{CBC}}}ID") == "B001-45"
    # Las boletas no llevan forma de pago.
    assert root.find(f"{{{CAC}}}PaymentTerms") is None
    cliente_id = root.find(
        f"{{{CAC}}}AccountingCustomerParty/{{{CAC}}}Party/"
        f"{{{CAC}}}PartyIdentification/{{{CBC}}}ID"
    )
    assert cliente_id.text == "45678912"
    assert cliente_id.get("schemeID") == "1"


def test_nota_credito_estructura(factura):
    nc = NotaCredito(
        serie="FC01", numero=7, emisor=factura.emisor, cliente=factura.cliente,
        fecha_emision=date(2026, 10, 16),
        afecta=factura, motivo="07",
        items=[Item("Mouse inalámbrico", 1, precio="59.00")],
    )
    root = _parse(nc)
    assert root.tag.endswith("}CreditNote")
    dr = root.find(f"{{{CAC}}}DiscrepancyResponse")
    assert dr.findtext(f"{{{CBC}}}ReferenceID") == "F001-123"
    assert dr.findtext(f"{{{CBC}}}ResponseCode") == "07"
    br = root.find(f"{{{CAC}}}BillingReference/{{{CAC}}}InvoiceDocumentReference")
    assert br.findtext(f"{{{CBC}}}ID") == "F001-123"
    assert br.findtext(f"{{{CBC}}}DocumentTypeCode") == "01"
    assert len(root.findall(f"{{{CAC}}}CreditNoteLine")) == 1
    assert root.find(f"{{{CAC}}}CreditNoteLine/{{{CBC}}}CreditedQuantity") is not None
    assert root.find(f"{{{CAC}}}LegalMonetaryTotal") is not None


def test_nota_debito_estructura(factura):
    nd = NotaDebito(
        serie="FD01", numero=2, emisor=factura.emisor, cliente=factura.cliente,
        fecha_emision=date(2026, 10, 16),
        afecta=factura, motivo="01",
        items=[Item("Interés por mora", 1, valor="50.00", unidad="ZZ")],
    )
    root = _parse(nd)
    assert root.tag.endswith("}DebitNote")
    assert root.find(f"{{{CAC}}}RequestedMonetaryTotal") is not None
    assert root.find(f"{{{CAC}}}DebitNoteLine/{{{CBC}}}DebitedQuantity") is not None


def test_item_exonerado_usa_tributo_9997(factura):
    from sunat_see import Afectacion

    factura.items = [Item("Libro", 1, precio="50.00", afectacion=Afectacion.EXONERADO)]
    root = _parse(factura)
    linea = root.find(f"{{{CAC}}}InvoiceLine")
    scheme_id = linea.find(
        f"{{{CAC}}}TaxTotal/{{{CAC}}}TaxSubtotal/{{{CAC}}}TaxCategory/"
        f"{{{CAC}}}TaxScheme/{{{CBC}}}ID"
    )
    assert scheme_id.text == "9997"
    assert linea.findtext(f"{{{CAC}}}TaxTotal/{{{CBC}}}TaxAmount") == "0.00"
