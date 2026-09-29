import base64
import uuid
from collections.abc import Callable
from typing import Final
from urllib.parse import urlsplit, urlunsplit

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

from mercari_alert_bot.shared.clock import Clock

DPOP_HEADER_NAME: Final = "DPoP"
DPOP_TOKEN_TYPE: Final = "dpop+jwt"
DPOP_SIGNING_ALGORITHM: Final = "ES256"
P256_COORDINATE_BYTES: Final = 32


def generate_signing_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def generate_uuid4_string() -> str:
    return str(uuid.uuid4())


def encode_base64url(raw_bytes: bytes) -> str:
    return base64.urlsafe_b64encode(raw_bytes).rstrip(b"=").decode("ascii")


def strip_query_and_fragment(target_url: str) -> str:
    parts = urlsplit(target_url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def build_public_jwk(signing_key: ec.EllipticCurvePrivateKey) -> dict[str, str]:
    public_numbers = signing_key.public_key().public_numbers()
    return {
        "crv": "P-256",
        "kty": "EC",
        "x": encode_base64url(public_numbers.x.to_bytes(P256_COORDINATE_BYTES, "big")),
        "y": encode_base64url(public_numbers.y.to_bytes(P256_COORDINATE_BYTES, "big")),
    }


class DpopProofFactory:
    def __init__(
        self,
        clock: Clock,
        signing_key: ec.EllipticCurvePrivateKey | None = None,
        generate_unique_id: Callable[[], str] = generate_uuid4_string,
    ) -> None:
        resolved_key = signing_key if signing_key is not None else generate_signing_key()
        if not isinstance(resolved_key.curve, ec.SECP256R1):
            raise ValueError(f"DPoP signing key must use P-256: {resolved_key.curve.name}")
        self._clock = clock
        self._signing_key = resolved_key
        self._generate_unique_id = generate_unique_id
        self._public_jwk = build_public_jwk(resolved_key)

    @property
    def public_jwk(self) -> dict[str, str]:
        return dict(self._public_jwk)

    def create_proof(self, http_method: str, target_url: str) -> str:
        claims = {
            "iat": int(self._clock.now().timestamp()),
            "jti": self._generate_unique_id(),
            "htu": strip_query_and_fragment(target_url),
            "htm": http_method.upper(),
            "uuid": self._generate_unique_id(),
        }
        headers = {"typ": DPOP_TOKEN_TYPE, "jwk": self._public_jwk}
        return jwt.encode(
            claims, self._signing_key, algorithm=DPOP_SIGNING_ALGORITHM, headers=headers
        )
