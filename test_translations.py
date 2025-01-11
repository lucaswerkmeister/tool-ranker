import pytest


@pytest.mark.parametrize('placeholder_message_key', [
    'index-placeholder-entity-id-wikidata',
    'index-placeholder-entity-id-commons',
])
def test_placeholder_plain_text(
        translations: dict[str, dict[str, str]],
        language_code: str,
        placeholder_message_key: str,
) -> None:
    assert '<' not in translations[language_code][placeholder_message_key]
