"""Firma digital XAdES-BES (enveloped) del XML UBL.

SUNAT exige que ``ds:Signature`` viva **dentro** de
``ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent``. ``signxml`` inserta
la firma como último hijo del root; luego se mueve a ``ExtensionContent``. La
transformación *enveloped-signature* excluye la firma del digest sin importar su
ubicación, así que moverla no invalida nada.

En BETA se puede firmar con un certificado autofirmado (SUNAT beta no valida el
certificado contra el RUC). En producción se usa el ``.pfx`` del emisor.
"""
from __future__ import annotations

import datetime as _dt

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from lxml import etree
from signxml import XMLSigner
from signxml.algorithms import (
    CanonicalizationMethod,
    DigestAlgorithm,
    SignatureConstructionMethod,
    SignatureMethod,
)

from .ubl import EXT

SIGNATURE_ID = "SignatureSP"

DS = "http://www.w3.org/2000/09/xmldsig#"


def generate_self_signed_cert(common_name: str = "SUNAT-SEE-BETA") -> tuple[bytes, bytes]:
    """Genera ``(cert_pem, key_pem)`` autofirmado RSA-2048. Solo para BETA/pruebas."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = _dt.datetime.now(_dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - _dt.timedelta(days=1))
        .not_valid_after(now + _dt.timedelta(days=3650))
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return cert_pem, key_pem


def load_pfx(pfx_bytes: bytes, password: str) -> tuple[bytes, bytes]:
    """Carga un ``.pfx``/``.p12`` del emisor → ``(cert_pem, key_pem)``."""
    from cryptography.hazmat.primitives.serialization import pkcs12

    key, cert, _extra = pkcs12.load_key_and_certificates(
        pfx_bytes, password.encode() if password else None
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return cert_pem, key_pem


def sign_xml(xml_bytes: bytes, cert_pem: bytes, key_pem: bytes) -> tuple[bytes, str]:
    """Firma el XML UBL y coloca la firma en ``ext:ExtensionContent``.

    Devuelve ``(xml_firmado, digest_value)``. El DigestValue es el *hash* del
    comprobante: se imprime en la representación impresa y forma parte del QR.
    """
    root = etree.fromstring(xml_bytes)

    signer = XMLSigner(
        method=SignatureConstructionMethod.enveloped,
        signature_algorithm=SignatureMethod.RSA_SHA256,
        digest_algorithm=DigestAlgorithm.SHA256,
        # SUNAT usa C14N 1.0 (REC-xml-c14n-20010315).
        c14n_algorithm=CanonicalizationMethod.CANONICAL_XML_1_0,
    )
    signed_root = signer.sign(root, key=key_pem, cert=cert_pem)

    signature = signed_root.find(f"{{{DS}}}Signature")
    signature.set("Id", SIGNATURE_ID)
    ext_content = signed_root.find(
        f"{{{EXT}}}UBLExtensions/{{{EXT}}}UBLExtension/{{{EXT}}}ExtensionContent"
    )
    signed_root.remove(signature)
    ext_content.append(signature)

    digest_el = signature.find(
        f"{{{DS}}}SignedInfo/{{{DS}}}Reference/{{{DS}}}DigestValue"
    )
    digest_value = digest_el.text if digest_el is not None else ""

    out = etree.tostring(signed_root, xml_declaration=True, encoding="UTF-8", standalone=False)
    return out, digest_value
