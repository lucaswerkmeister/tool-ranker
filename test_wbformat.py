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
