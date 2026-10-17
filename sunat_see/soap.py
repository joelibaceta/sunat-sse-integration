"""Cliente SOAP del ``billService`` de SUNAT (envío directo, sin OSE).

Sobre SOAP 1.1 con autenticación WSSE UsernameToken y el comprobante comprimido
en ZIP + base64. Se usa ``requests`` directamente (el envelope es simple; evita
la dependencia de ``zeep``).

Operaciones: ``sendBill`` (factura/notas, síncrono → CDR), ``sendSummary``
(resumen diario de boletas, asíncrono → ticket) y ``getStatus`` (estado del ticket).
"""
from __future__ import annotations

import base64
import io
import zipfile
from dataclasses import dataclass
from xml.sax.saxutils import escape

import requests
from lxml import etree

from .exceptions import RespuestaInvalida, SoapFault

SOAPENV = "http://schemas.xmlsoap.org/soap/envelope/"
WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
SERVICE = "http://service.sunat.gob.pe"

_ENVELOPE = """<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="{soapenv}" xmlns:ser="{service}" xmlns:wsse="{wsse}">
  <soapenv:Header>
    <wsse:Security>
      <wsse:UsernameToken>
        <wsse:Username>{username}</wsse:Username>
        <wsse:Password>{password}</wsse:Password>
      </wsse:UsernameToken>
    </wsse:Security>
  </soapenv:Header>
  <soapenv:Body>{body}</soapenv:Body>
</soapenv:Envelope>"""


def zip_document(xml_bytes: bytes, doc_name: str) -> bytes:
    """Comprime el XML en un ZIP con el nombre que exige SUNAT (``<doc_name>.xml``)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{doc_name}.xml", xml_bytes)
    return buf.getvalue()


def _find_text(root, local_name: str) -> str | None:
    """Busca el texto de un elemento por nombre local, con o sin namespace."""
    el = root.find(f".//{{*}}{local_name}")
    if el is None:
        el = root.find(f".//{local_name}")
    return el.text if el is not None and el.text else None


def _raise_if_fault(root) -> None:
    fault = root.find(f".//{{{SOAPENV}}}Fault")
    if fault is not None:
        code = (fault.findtext("faultcode") or "").strip()
        msg = (fault.findtext("faultstring") or "").strip()
        raise SoapFault(code or "SOAP-FAULT", msg or "SOAP Fault")


@dataclass
class SoapClient:
    endpoint: str
    username: str
    password: str
    timeout: int = 60

    def _call(self, body: str) -> etree._Element:
        envelope = _ENVELOPE.format(
            soapenv=SOAPENV, service=SERVICE, wsse=WSSE,
            username=escape(self.username), password=escape(self.password),
            body=body,
        )
        resp = requests.post(
            self.endpoint,
            data=envelope.encode("utf-8"),
            headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""},
            timeout=self.timeout,
        )
        # SUNAT devuelve 500 con un Fault SOAP en el body ante errores de negocio.
        try:
            root = etree.fromstring(resp.content)
        except etree.XMLSyntaxError as exc:
            raise RespuestaInvalida(f"Respuesta no-XML de SUNAT (HTTP {resp.status_code})") from exc
        _raise_if_fault(root)
        return root

    def send_bill(self, doc_name: str, signed_xml: bytes) -> bytes:
        """Envía un comprobante firmado (``sendBill``) y devuelve el ZIP del CDR.

        ``doc_name`` = ``<RUC>-<tipo>-<serie>-<numero>`` (sin extensión).
        """
        zip_b64 = base64.b64encode(zip_document(signed_xml, doc_name)).decode("ascii")
        body = (f"<ser:sendBill><fileName>{doc_name}.zip</fileName>"
                f"<contentFile>{zip_b64}</contentFile></ser:sendBill>")
        root = self._call(body)
        content = _find_text(root, "applicationResponse")
        if not content:
            raise RespuestaInvalida("Respuesta SOAP sin applicationResponse")
        return base64.b64decode(content)

    def send_summary(self, doc_name: str, signed_xml: bytes) -> str:
        """Envía un resumen diario (``sendSummary``) y devuelve el número de ticket."""
        zip_b64 = base64.b64encode(zip_document(signed_xml, doc_name)).decode("ascii")
        body = (f"<ser:sendSummary><fileName>{doc_name}.zip</fileName>"
                f"<contentFile>{zip_b64}</contentFile></ser:sendSummary>")
        root = self._call(body)
        ticket = _find_text(root, "ticket")
        if not ticket:
            raise RespuestaInvalida("Respuesta SOAP sin ticket")
        return ticket.strip()

    def get_status(self, ticket: str) -> tuple[str, bytes | None]:
        """Consulta un ticket (``getStatus``) → ``(status_code, cdr_zip | None)``.

        ``status_code``: ``0`` procesado OK, ``98`` en proceso, ``99`` procesado
        con errores (puede traer CDR).
        """
        body = f"<ser:getStatus><ticket>{escape(ticket)}</ticket></ser:getStatus>"
        root = self._call(body)
        status = _find_text(root, "statusCode")
        if status is None:
            raise RespuestaInvalida("Respuesta SOAP sin statusCode")
        content = _find_text(root, "content")
        return status.strip(), (base64.b64decode(content) if content else None)
