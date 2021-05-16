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


def test_parse_statement_ids_list():
    input = '''
Q1$123
Q2$123
Q1$456
q2$456
P3$123
'''.strip()
    statement_ids_by_entity_id = ranker.parse_statement_ids_list(input)
    assert statement_ids_by_entity_id == {
        'Q1': ['Q1$123', 'Q1$456'],
        'Q2': ['Q2$123', 'q2$456'],
        'P3': ['P3$123'],
    }


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


@pytest.mark.parametrize('with_property_id', [
    True,
    False,
])
def test_statements_set_rank_to(with_property_id: bool):
    unrelated_statement = {'id': 'X', 'rank': 'normal'}
    unselected_statement = {'id': 'Y', 'rank': 'normal'}
    unedited_statement = {'id': 'a', 'rank': 'preferred'}
    edited_statement = {'id': 'b', 'rank': 'normal'}
    property_id = 'P1'
    unrelated_property_id = 'P2'
    statement_ids = {'a', 'b'}
    rank = 'preferred'
    statements = {
        property_id: [
            unselected_statement,
            unedited_statement,
            edited_statement,
        ],
        unrelated_property_id: [
            unrelated_statement,
        ],
    }

    statements, edited_statements = ranker.statements_set_rank_to(
        statement_ids,
        rank,
        statements,
        property_id if with_property_id else None,
    )

    assert edited_statements == 1
    assert property_id in statements
    assert edited_statement in statements[property_id]
    assert edited_statement['rank'] == 'preferred'
    assert unedited_statement['rank'] == 'preferred'
    assert unselected_statement['rank'] == 'normal'
    assert unrelated_statement['rank'] == 'normal'


@pytest.mark.parametrize('with_property_id', [
    True,
    False,
])
def test_statements_increment_rank(with_property_id: bool):
    unrelated_statement = {'id': 'X', 'rank': 'normal'}
    unselected_statement = {'id': 'Y', 'rank': 'normal'}
    unedited_statement = {'id': 'a', 'rank': 'preferred'}
    edited_statement = {'id': 'b', 'rank': 'normal'}
    property_id = 'P1'
    unrelated_property_id = 'P2'
    statement_ids = {'a', 'b'}
    statements = {
        property_id: [
            unselected_statement,
            unedited_statement,
            edited_statement,
        ],
        unrelated_property_id: [
            unrelated_statement,
        ],
    }

    statements, edited_statements = ranker.statements_increment_rank(
        statement_ids,
        statements,
        property_id if with_property_id else None,
    )

    assert edited_statements == 1
    assert property_id in statements
    assert edited_statement in statements[property_id]
    assert edited_statement['rank'] == 'preferred'
    assert unedited_statement['rank'] == 'preferred'
    assert unselected_statement['rank'] == 'normal'
    assert unrelated_statement['rank'] == 'normal'
