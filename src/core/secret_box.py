"""Symmetric encryption of secrets stored in the DB (e.g. Atlassian API tokens),
with the Fernet key in ``MBARE_PILOT_SECRET_KEY``. Without a key the app still
starts: only saving or reading a secret fails, explaining what to set."""
from cryptography.fernet import Fernet, InvalidToken

from core.error import ValidationError

GENERATE_HINT = 'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'


class SecretBox:

    def __init__(self, key: str | None):
        self._fernet = self._build(key) if key else None

    @property
    def is_configured(self) -> bool:
        return self._fernet is not None

    def encrypt(self, plain: str) -> str:
        return self._require().encrypt(plain.encode()).decode()

    def decrypt(self, token: str) -> str | None:
        """The plain text, or None when ``token`` was not encrypted with this key
        (key changed, or a value saved before encryption)."""
        try:
            return self._require().decrypt(token.encode()).decode()
        except InvalidToken:
            return None

    def _require(self) -> Fernet:
        if self._fernet is None:
            raise ValidationError(
                f"Chiave di cifratura mancante: imposta MBARE_PILOT_SECRET_KEY nel .env (generala con {GENERATE_HINT}) "
                "e riavvia l'app."
            )
        return self._fernet

    @staticmethod
    def _build(key: str) -> Fernet:
        try:
            return Fernet(key.encode())
        except ValueError as exc:
            raise ValidationError(
                f"MBARE_PILOT_SECRET_KEY non valida: deve essere una chiave Fernet (generala con {GENERATE_HINT})."
            ) from exc
