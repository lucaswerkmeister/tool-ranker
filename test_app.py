import flask
import pytest  # type: ignore

import app as ranker


@pytest.fixture
def client():
    ranker.app.testing = True
    client = ranker.app.test_client()

    with client:
        yield client
    # request context stays alive until the fixture is closed


def test_csrf_token_generate():
    with ranker.app.test_request_context():
        token = ranker.csrf_token()
        assert token != ''


def test_csrf_token_save():
    with ranker.app.test_request_context() as context:
        token = ranker.csrf_token()
        assert token == context.session['csrf_token']


def test_csrf_token_load():
    with ranker.app.test_request_context() as context:
        context.session['csrf_token'] = 'test token'
        assert ranker.csrf_token() == 'test token'


def test_index_redirect(client):
    response = client.post('/',
                           data={'wiki': 'www.wikidata.org',
                                 'entity_id': 'Q4115189',
                                 'property_id': 'P361'})
    expected_redirect = 'http://localhost/edit/www.wikidata.org/Q4115189/P361/'
    assert response.headers['location'] == expected_redirect


def test_index_redirect_mediainfo(client):
    response = client.post('/',
                           data={'wiki': 'commons.wikimedia.org',
                                 'entity_id': 'File:DSC 0484 2-01.jpg',
                                 'property_id': 'P180'})
    expected_redirect = ('http://localhost/edit'
                         '/commons.wikimedia.org/M79869096/P180/')
    assert response.headers['location'] == expected_redirect


def test_format_value_escapes_html():
    value = {'value': '<script>alert("!Mediengruppe Bitnik");</script>',
             'type': 'string'}
    expected = flask.Markup(r'&lt;script&gt;alert(&#34;!Mediengruppe'
                            r' Bitnik&#34;);&lt;/script&gt;')
    assert ranker.format_value('test.wikidata.org', 'P95', value) == expected


def test_get_entities():
    class FakeSession:
        def get(self, ids, **kwargs):
            assert len(ids) <= 50
            return {'entities': {id: f'entity {id}' for id in ids}}

    entity_ids = [f'Q{id}' for id in range(1, 120)]
    entities = ranker.get_entities(FakeSession(), entity_ids)
    assert entities == {id: f'entity {id}' for id in entity_ids}


@pytest.mark.parametrize('rank, expected', [
    ('deprecated', 'normal'),
    ('normal', 'preferred'),
    ('preferred', 'preferred'),
])
def test_increment_rank(rank, expected):
    assert ranker.increment_rank(rank) == expected
