"""Parseo del CDR (Constancia de Recepción) que devuelve SUNAT.

El CDR viene en un ZIP cuyo contenido es un ``ApplicationResponse`` UBL firmado
por SUNAT. El resultado está en ``cac:DocumentResponse/cac:Response``:

- ``cbc:ResponseCode`` = ``0`` → aceptado; 2000–3999 → rechazado; 4000+ → aceptado con observaciones.
- ``cbc:Description`` = mensaje legible.

El CDR es la prueba legal de aceptación: guárdalo siempre.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

from lxml import etree

from .exceptions import RespuestaInvalida

CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"


@dataclass(frozen=True)
class Cdr:
    codigo: str          # "0" = aceptado
    descripcion: str
    xml: bytes           # ApplicationResponse crudo (conservar)
    aceptado: bool

    @property
    def observado(self) -> bool:
        """Aceptado con observaciones (códigos 4000+)."""
        return self.codigo.isdigit() and int(self.codigo) >= 4000


def parse_cdr_zip(cdr_zip: bytes) -> Cdr:
    with zipfile.ZipFile(io.BytesIO(cdr_zip)) as zf:
        # El CDR es el XML del ZIP (normalmente ``R-<doc_name>.xml``).
        name = next((n for n in zf.namelist() if n.lower().endswith(".xml")), None)
        if name is None:
            raise RespuestaInvalida("CDR ZIP sin XML")
        xml = zf.read(name)

    root = etree.fromstring(xml)
    resp = root.find(f".//{{{CAC}}}DocumentResponse/{{{CAC}}}Response")
    if resp is None:
        raise RespuestaInvalida("CDR sin cac:Response")
    codigo = (resp.findtext(f"{{{CBC}}}ResponseCode") or "").strip()
    descripcion = (resp.findtext(f"{{{CBC}}}Description") or "").strip()
    return Cdr(codigo=codigo, descripcion=descripcion, xml=xml, aceptado=(codigo == "0"))
