import pytest
from cryptography.fernet import Fernet

from core.error import ValidationError
from core.secret_box import SecretBox


def test_round_trip():
    box = SecretBox(Fernet.generate_key().decode())

    encrypted = box.encrypt("tok-123")

    assert encrypted != "tok-123"
    assert box.decrypt(encrypted) == "tok-123"


def test_other_key_or_plain_value_cannot_be_decrypted():
    encrypted = SecretBox(Fernet.generate_key().decode()).encrypt("tok-123")
    box = SecretBox(Fernet.generate_key().decode())

    assert box.decrypt(encrypted) is None
    assert box.decrypt("tok-123") is None


def test_missing_key_explains_what_to_set():
    box = SecretBox(None)

    assert box.is_configured is False
    with pytest.raises(ValidationError, match="MBARE_PILOT_SECRET_KEY"):
        box.encrypt("x")


def test_invalid_key_rejected():
    with pytest.raises(ValidationError, match="Fernet"):
        SecretBox("not-a-key")
