from decimal import Decimal

from sunat_see import Afectacion, Item


def test_precio_con_igv_calcula_valor_neto(factura):
    _, tot = factura.calcular()
    # 2 × 1180 + 59 = 2419 con IGV → neto 2050, IGV 369
    assert tot.gravado == Decimal("2050.00")
    assert tot.igv == Decimal("369.00")
    assert tot.total == Decimal("2419.00")


def test_valor_sin_igv_calcula_total(factura):
    factura.items = [Item("Servicio", 1, valor=Decimal("1000.00"), unidad="ZZ")]
    _, tot = factura.calcular()
    assert tot.gravado == Decimal("1000.00")
    assert tot.igv == Decimal("180.00")
    assert tot.total == Decimal("1180.00")


def test_items_exonerados_no_llevan_igv(factura):
    factura.items = [
        Item("Libro", 1, precio=Decimal("50.00"), afectacion=Afectacion.EXONERADO),
        Item("Gravado", 1, valor=Decimal("100.00")),
    ]
    _, tot = factura.calcular()
    assert tot.exonerado == Decimal("50.00")
    assert tot.gravado == Decimal("100.00")
    assert tot.igv == Decimal("18.00")
    assert tot.total == Decimal("168.00")


def test_total_property(boleta):
    assert boleta.total == Decimal("15.00")
    assert boleta.full_id == "B001-45"
