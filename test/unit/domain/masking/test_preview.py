"""Masking of a free text before it is sent: the project's map, mask{term},
automatic recognition only for this text, and the aliases' positions."""
import pytest

from domain.masking.preview import masked_text, tagged_terms, unmask, without_tags
from models.domain.masking import MaskCategory, MaskEntry, MaskOrigin

MAP = [
    MaskEntry(category=MaskCategory.PERSON, value="Marco", alias="PERSONA_1"),
    MaskEntry(category=MaskCategory.REPOSITORY, value="api", alias="REPO_1"),
    MaskEntry(category=MaskCategory.TERM, value="Acme Spa", alias="TERMINE_1"),
]


def _aliases(result) -> list[tuple[str, str]]:
    return [(span.alias, span.origin.value) for span in result.spans]


def test_tags_are_listed_once_and_removed_from_the_text():
    text = "sentire mask{Marco} e mask{ Acme Spa } poi ancora mask{Marco}, mask{ } vuoto"

    assert tagged_terms(text) == ["Marco", "Acme Spa"]
    assert without_tags(text) == "sentire Marco e Acme Spa poi ancora Marco,  vuoto"
    assert tagged_terms("mask{su due\nrighe}") == []  # one line only


def test_the_map_and_the_tags_give_their_aliases_with_their_positions():
    result = masked_text("Marco chiede ad Acme Spa del repo api (non rapid)", MAP, tagged=["Acme Spa"])

    assert result.text == "PERSONA_1 chiede ad TERMINE_1 del repo REPO_1 (non rapid)"
    assert _aliases(result) == [("PERSONA_1", "map"), ("TERMINE_1", "tag"), ("REPO_1", "map")]
    assert all(result.text[span.start:span.end] == span.alias for span in result.spans)
    assert result.temporary == {}  # nothing automatic


@pytest.mark.parametrize(("text", "alias", "value"), [
    ("scrivi a ada.lovelace+test@acme.co.uk domani", "MAIL_1", "ada.lovelace+test@acme.co.uk"),
    ("vedi https://acme.atlassian.net/browse/NAV-7.", "URL_1", "https://acme.atlassian.net/browse/NAV-7"),
    ("vedi www.acme.it/login, poi", "URL_1", "www.acme.it/login"),
    ("il server 10.0.12.254 è giù", "IP_1", "10.0.12.254"),
    ("token ghp_abcdefghijklmnopqrstuvwxyz0123 scaduto", "CHIAVE_1", "ghp_abcdefghijklmnopqrstuvwxyz0123"),
    ("chiave sk-proj-abcdefghijklmnop1234", "CHIAVE_1", "sk-proj-abcdefghijklmnop1234"),
    ("aws AKIAABCDEFGHIJKLMNOP", "CHIAVE_1", "AKIAABCDEFGHIJKLMNOP"),
    ("jwt eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.SflKxwRJSMeKKF2QT4", "CHIAVE_1", "eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.SflKxwRJSMeKKF2QT4"),
    ("password=Segreta!2024 per il db", "CHIAVE_1", "Segreta!2024"),
    ("api_key: abc123def", "CHIAVE_1", "abc123def"),
    ("hash 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08 trovato", "CHIAVE_1",
     "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"),
])
def test_recognizable_shapes_are_masked_only_for_this_text(text, alias, value):
    result = masked_text(text, [])

    assert value not in result.text and alias in result.text
    assert result.temporary == {alias: value}
    assert _aliases(result) == [(alias, "auto")]


@pytest.mark.parametrize("text", [
    "rilascio della v1.2.3.4.5 e del modulo 2.0",  # versions are not IPs
    "il ticket NAV-1234 e la issue 999",
    "una parola_lunghissima_ma_senza_numeri_che_non_e_una_chiave",  # no digit: not a key
    "MARCO in maiuscolo non è nella mappa vuota",
])
def test_ordinary_text_stays_in_clear(text):
    assert masked_text(text, []).text == text


def test_the_same_value_gets_the_same_alias_and_the_map_wins_over_recognition():
    entries = [MaskEntry(category=MaskCategory.EMAIL, value="ada@acme.it", alias="EMAIL_4")]

    result = masked_text("ada@acme.it, bob@acme.it e di nuovo bob@acme.it", entries)

    assert result.text == "EMAIL_4, MAIL_1 e di nuovo MAIL_1"
    assert [span.origin for span in result.spans] == [MaskOrigin.MAP, MaskOrigin.AUTO, MaskOrigin.AUTO]


def test_unmask_gives_back_the_map_and_the_temporary_values():
    result = masked_text("Marco scrive a bob@acme.it da 10.0.0.1", MAP)

    answer = "Chiedere a PERSONA_1 di scrivere a MAIL_1 (server IP_1, ignoto IP_9)"

    assert unmask(answer, MAP, result.temporary) == "Chiedere a Marco di scrivere a bob@acme.it (server 10.0.0.1, ignoto IP_9)"
    assert unmask("PERSONA_1", MAP, {}) == "Marco"
