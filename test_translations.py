import pytest

from query_service import wikis_with_query_service, query_service_id


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


@pytest.mark.parametrize('message_key_prefix', [
    # app.py, batch_query_collective_message()
    'batch-query-collective-input-',
    # app.py, batch_query_individual_message()
    'batch-query-individual-input-',
])
@pytest.mark.parametrize('wiki', wikis_with_query_service())
def test_query_service_messages_defined(
        translations: dict[str, dict[str, str]],
        message_key_prefix: str,
        wiki: str,
) -> None:
    message_key = message_key_prefix + query_service_id(wiki)
    assert message_key in translations['en']
