from markupsafe import Markup
import mwapi  # type: ignore
import pytest
import wbformat


@pytest.mark.filterwarnings('ignore::bs4.MarkupResemblesLocatorWarning')
def test_format_value_escapes_html():
    session = mwapi.Session('https://test.wikidata.org',
                            user_agent='Ranker unit tests')
    value = {'value': '<script>alert("!Mediengruppe Bitnik");</script>',
             'type': 'string'}
    expected = Markup(r'&lt;script&gt;alert("!Mediengruppe'
                      r' Bitnik");&lt;/script&gt;')
    assert wbformat.format_value(session, 'en', 'P95', value) == expected


def test_format_entity_P31():
    session = mwapi.Session('https://www.wikidata.org',
                            user_agent='Ranker unit tests')
    expected = Markup(r'<a title="Property:P31"'
                      r' href="https://www.wikidata.org/wiki'
                      r'/Property:P31">instance of</a>')
    assert wbformat.format_entity(session, 'en', 'P31') == expected


def test_prefetch_entities():
    class FakeSession:
        host = 'host'
        get_calls = 0

        def get(self, ids, **kwargs):
            self.get_calls += 1
            return {'wbformatentities': {
                entity_id: f'label of {entity_id}' for entity_id in ids
            }}
    session = FakeSession()
    entity_ids = ([f'P{id}' for id in range(1, 60)]
                  + [f'Q{id}' for id in range(1, 60)])
    wbformat.prefetch_entities(session, 'en', entity_ids)
    assert session.get_calls == 3
    for id in range(1, 60):
        for entity_id in [f'P{id}', f'Q{id}']:
            key = ('host', 'en', entity_id)
        assert wbformat.format_entity_cache[key] == f'label of {entity_id}'
