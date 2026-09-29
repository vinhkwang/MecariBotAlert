import base64
import itertools
from datetime import UTC, datetime
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from mercari_alert_bot.infrastructure.sources.dpop_proof_factory import (
    DpopProofFactory,
    generate_signing_key,
)
from tests.shared.fakes import FrozenClock

FROZEN_TIME = datetime(2026, 9, 29, 12, 0, 0, tzinfo=UTC)
SEARCH_URL = "https://api.mercari.jp/v2/entities:search"
DETAIL_URL = "https://api.mercari.jp/items/get"


def build_factory(**overrides: Any) -> DpopProofFactory:
    return DpopProofFactory(FrozenClock(FROZEN_TIME), **overrides)


def decode_unpadded_base64url(encoded: str) -> bytes:
    return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))


def read_claims(proof: str) -> dict[str, Any]:
    return dict(jwt.decode(proof, options={"verify_signature": False}))


def test_proof_signature_verifies_with_embedded_jwk() -> None:
    proof = build_factory().create_proof("POST", SEARCH_URL)

    embedded_jwk = jwt.get_unverified_header(proof)["jwk"]
    embedded_key = jwt.PyJWK(embedded_jwk).key
    verified_claims = jwt.decode(
        proof, embedded_key, algorithms=["ES256"], options={"verify_iat": False}
    )

    assert verified_claims["htm"] == "POST"


def test_proof_header_declares_dpop_type_and_es256() -> None:
    header = jwt.get_unverified_header(build_factory().create_proof("POST", SEARCH_URL))

    assert header["typ"] == "dpop+jwt"
    assert header["alg"] == "ES256"


def test_public_jwk_has_no_private_member() -> None:
    public_jwk = build_factory().public_jwk

    assert set(public_jwk) == {"crv", "kty", "x", "y"}
    assert public_jwk["crv"] == "P-256"
    assert public_jwk["kty"] == "EC"


def test_jwk_coordinates_are_unpadded_32_byte_base64url() -> None:
    signing_key = generate_signing_key()
    public_jwk = build_factory(signing_key=signing_key).public_jwk
    public_numbers = signing_key.public_key().public_numbers()

    assert "=" not in public_jwk["x"] + public_jwk["y"]
    assert len(decode_unpadded_base64url(public_jwk["x"])) == 32
    assert len(decode_unpadded_base64url(public_jwk["y"])) == 32
    assert int.from_bytes(decode_unpadded_base64url(public_jwk["x"]), "big") == public_numbers.x
    assert int.from_bytes(decode_unpadded_base64url(public_jwk["y"]), "big") == public_numbers.y


def test_issued_at_comes_from_injected_clock() -> None:
    claims = read_claims(build_factory().create_proof("POST", SEARCH_URL))

    assert claims["iat"] == int(FROZEN_TIME.timestamp())


def test_method_is_upper_cased() -> None:
    claims = read_claims(build_factory().create_proof("post", SEARCH_URL))

    assert claims["htm"] == "POST"


def test_target_url_query_and_fragment_are_stripped() -> None:
    claims = read_claims(build_factory().create_proof("GET", f"{DETAIL_URL}?id=m1#section"))

    assert claims["htu"] == DETAIL_URL


def test_each_proof_has_fresh_jti_and_uuid() -> None:
    factory = build_factory()

    first_claims = read_claims(factory.create_proof("POST", SEARCH_URL))
    second_claims = read_claims(factory.create_proof("POST", SEARCH_URL))

    unique_ids = {
        first_claims["jti"],
        first_claims["uuid"],
        second_claims["jti"],
        second_claims["uuid"],
    }
    assert len(unique_ids) == 4


def test_injected_id_generator_is_used() -> None:
    counter = itertools.count(1)
    factory = build_factory(generate_unique_id=lambda: f"id-{next(counter)}")

    claims = read_claims(factory.create_proof("POST", SEARCH_URL))

    assert claims["jti"] == "id-1"
    assert claims["uuid"] == "id-2"


def test_same_factory_reuses_one_key() -> None:
    factory = build_factory()

    first_header = jwt.get_unverified_header(factory.create_proof("POST", SEARCH_URL))
    second_header = jwt.get_unverified_header(factory.create_proof("GET", DETAIL_URL))

    assert first_header["jwk"] == second_header["jwk"]


def test_separate_factories_generate_different_keys() -> None:
    assert build_factory().public_jwk != build_factory().public_jwk


def test_non_p256_key_is_rejected() -> None:
    wrong_curve_key = ec.generate_private_key(ec.SECP384R1())

    with pytest.raises(ValueError, match="P-256"):
        build_factory(signing_key=wrong_curve_key)
