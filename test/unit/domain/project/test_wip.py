"""The WIP note: the new text after the last sign, paragraphs, the sign."""
from datetime import datetime

from domain.project import wip

WHEN = datetime(2026, 11, 5, 14, 30)


def test_without_a_sign_all_the_text_is_new_and_after_it_only_what_follows():
    assert wip.pending("  primo appunto\n\nsecondo  ") == "primo appunto\n\nsecondo"
    content = "vecchio\n\n—— elaborato il 01/11 09:00 ——\n\nmezzo\n\n—— elaborato il 03/11 10:00 ——\n\nnuovo\n"
    assert wip.pending(content) == "nuovo"
    assert wip.pending("già tutto\n—— elaborato il 01/11 09:00 ——\n") == ""
    assert wip.pending("una riga —— elaborato il 01/11 09:00 —— in mezzo") != ""  # a sign is a whole line


def test_paragraphs_and_words():
    text = "uno due\ntre\n\n\n  \nquattro\n\ncinque"

    assert wip.paragraphs(text) == ["uno due\ntre", "quattro", "cinque"]
    assert wip.words(text) == 5
    assert wip.first_paragraphs(text, 2) == "uno due\ntre\n\nquattro"
    assert wip.first_paragraphs(text, None) == wip.first_paragraphs(text, 10) == "uno due\ntre\n\nquattro\n\ncinque"
    assert wip.first_paragraphs(text, 0) == "uno due\ntre"  # at least one


def test_the_sign_goes_after_the_processed_paragraphs_and_the_diary_stays():
    content = "diario\n\n—— elaborato il 01/11 09:00 ——\n\nprimo\n\n\nsecondo\n\nterzo\n"

    assert wip.with_sign(content, "primo\n\nsecondo", WHEN) == (
        "diario\n\n—— elaborato il 01/11 09:00 ——\n\nprimo\n\nsecondo\n\n—— elaborato il 05/11 14:30 ——\n\nterzo\n"
    )
    signed = wip.with_sign("solo questo", "solo questo", WHEN)
    assert signed == "solo questo\n\n—— elaborato il 05/11 14:30 ——\n" and wip.pending(signed) == ""


def test_no_sign_when_the_new_text_changed_meanwhile():
    assert wip.with_sign("primo cambiato\n\nsecondo", "primo\n\nsecondo", WHEN) is None
    assert wip.with_sign("primo", "", WHEN) is None
