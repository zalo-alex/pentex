import datetime
import ipaddress
import logging
import os

logger = logging.getLogger(__name__)

CERT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'instance', 'certs'
)
DEFAULT_CERT_FILE = os.path.join(CERT_DIR, 'cert.pem')
DEFAULT_KEY_FILE = os.path.join(CERT_DIR, 'key.pem')


def _generate_self_signed_cert(cert_path, key_path):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = key.public_key()

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, 'PENTEX self-signed'),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    ski = x509.SubjectKeyIdentifier.from_public_key(public_key)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName('localhost'),
                x509.IPAddress(ipaddress.ip_address('127.0.0.1')),
                x509.IPAddress(ipaddress.ip_address('::1')),
            ]),
            critical=False,
        )
        # Windows Schannel (curl.exe, PowerShell, Edge) rejects self-signed
        # certs missing these v3 extensions with a "bad_certificate" alert
        # instead of the expected "unknown_ca" — browsers on other stacks
        # tolerate their absence, but Schannel does not.
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_encipherment=True, content_commitment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .add_extension(ski, critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(ski),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    os.makedirs(os.path.dirname(cert_path), exist_ok=True)
    with open(key_path, 'wb') as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    with open(cert_path, 'wb') as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass


def get_ssl_context():
    """Return (certfile, keyfile) paths to use for HTTPS.

    Uses SSL_CERT_FILE/SSL_KEY_FILE from the environment if both are set.
    Otherwise generates (or reuses a previously generated) self-signed
    certificate under instance/certs/, so restarts don't regenerate it and
    the browser doesn't warn about a new cert every time.
    """
    cert_file = os.environ.get('SSL_CERT_FILE')
    key_file = os.environ.get('SSL_KEY_FILE')

    if cert_file and key_file:
        if not os.path.isfile(cert_file) or not os.path.isfile(key_file):
            raise FileNotFoundError(
                f'SSL_CERT_FILE/SSL_KEY_FILE set but not found: {cert_file}, {key_file}'
            )
        logger.info('Using configured TLS certificate: %s', cert_file)
        return cert_file, key_file

    if not (os.path.isfile(DEFAULT_CERT_FILE) and os.path.isfile(DEFAULT_KEY_FILE)):
        logger.warning(
            'No SSL_CERT_FILE/SSL_KEY_FILE configured; generating a self-signed '
            'certificate at %s (browsers will show a trust warning)', CERT_DIR
        )
        _generate_self_signed_cert(DEFAULT_CERT_FILE, DEFAULT_KEY_FILE)
    else:
        logger.info('Reusing previously generated self-signed certificate: %s', DEFAULT_CERT_FILE)

    return DEFAULT_CERT_FILE, DEFAULT_KEY_FILE
