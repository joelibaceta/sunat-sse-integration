"""sunat-see — SDK declarativo para facturación electrónica SUNAT (Perú).

Describe el comprobante (qué se vende, a quién, cómo se paga) y el SDK se
encarga del resto: totales e IGV, XML UBL 2.1, leyenda en letras, firma
XAdES-BES, envío al billService y lectura del CDR.

::

    from sunat_see import Emisor, Cliente, Item, Factura, SunatClient

    factura = Factura(
        serie="F001", numero=1,
        emisor=Emisor(ruc="20123456789", razon_social="MI EMPRESA S.A.C."),
        cliente=Cliente.con_ruc("20600055519", "CLIENTE S.A.C."),
        items=[Item("Laptop 14\"", 2, precio="1180.00")],
    )
    resultado = SunatClient.beta(ruc="20123456789").enviar(factura)
"""
from .catalogs import (
    Afectacion,
    MotivoNotaCredito,
    MotivoNotaDebito,
    TipoComprobante,
    TipoDocIdentidad,
    Unidad,
)
from .cdr import Cdr, parse_cdr_zip
from .client import (
    ENDPOINT_BETA,
    ENDPOINT_PRODUCCION,
    Firmado,
    Resultado,
    ResultadoTicket,
    ResumenEnviado,
    SunatClient,
)
from .documents import Boleta, Factura, LineaCalculada, NotaCredito, NotaDebito, Totales
from .exceptions import RespuestaInvalida, SoapFault, SunatError, ValidacionError
from .letras import monto_en_letras
from .models import Cliente, Contado, Credito, Cuota, Emisor, Item, Referencia
from .summary import ResumenDiario

__version__ = "0.1.0"

__all__ = [
    # Documentos
    "Factura",
    "Boleta",
    "NotaCredito",
    "NotaDebito",
    "ResumenDiario",
    # Bloques
    "Emisor",
    "Cliente",
    "Item",
    "Contado",
    "Credito",
    "Cuota",
    "Referencia",
    "Totales",
    "LineaCalculada",
    # Catálogos
    "TipoComprobante",
    "TipoDocIdentidad",
    "Afectacion",
    "Unidad",
    "MotivoNotaCredito",
    "MotivoNotaDebito",
    # Cliente / resultados
    "SunatClient",
    "Firmado",
    "Resultado",
    "ResumenEnviado",
    "ResultadoTicket",
    "Cdr",
    "parse_cdr_zip",
    "ENDPOINT_BETA",
    "ENDPOINT_PRODUCCION",
    # Utilidades
    "monto_en_letras",
    # Errores
    "SunatError",
    "ValidacionError",
    "SoapFault",
    "RespuestaInvalida",
]
