import flask
import mwapi  # type: ignore
import wbformat


def test_format_value_escapes_html():
    session = mwapi.Session('https://test.wikidata.org',
                            user_agent='Ranker unit tests')
    value = {'value': '<script>alert("!Mediengruppe Bitnik");</script>',
             'type': 'string'}
    expected = flask.Markup(r'&lt;script&gt;alert(&#34;!Mediengruppe'
                            r' Bitnik&#34;);&lt;/script&gt;')
    assert wbformat.format_value(session, 'P95', value) == expected


def test_format_property_P31():
    session = mwapi.Session('https://www.wikidata.org',
                            user_agent='Ranker unit tests')
    expected = flask.Markup(r'<a title="Property:P31"'
                            r' href="https://www.wikidata.org/wiki'
                            r'/Property:P31">instance of</a>')
    assert wbformat.format_property(session, 'P31') == expected


def test_prefetch_properties():
    class FakeSession:
        host = 'host'
        get_calls = 0

        def get(self, ids, **kwargs):
            self.get_calls += 1
            return {'wbformatentities': {
                property_id: f'label of {property_id}' for property_id in ids
            }}
    session = FakeSession()
    property_ids = [f'P{id}' for id in range(1, 125)]
    wbformat.prefetch_properties(session, property_ids)
    assert session.get_calls == 3
    for id in range(1, 125):
        key = ('host', f'P{id}')
        assert wbformat.format_property_cache[key] == f'label of P{id}'
