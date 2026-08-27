from research_navigator.security import hash_password, hash_token, verify_password


def test_password_hash_round_trip_and_wrong_password_rejected() -> None:
    encoded = hash_password("correct horse battery staple")

    assert encoded.startswith("pbkdf2_sha256$")
    assert verify_password("correct horse battery staple", encoded) is True
    assert verify_password("incorrect", encoded) is False
    assert "correct horse" not in encoded


def test_token_hash_is_deterministic_and_not_plaintext() -> None:
    token = "secret-session-token"
    assert hash_token(token) == hash_token(token)
    assert hash_token(token) != token
