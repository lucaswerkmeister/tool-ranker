import flask
import pytest  # type: ignore
from typing import Optional

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


@pytest.mark.parametrize('uri, wiki, statement_id', [
    ('http://www.wikidata.org/entity/statement/Q474472-dcf39f47-4275-6529-96f5-94808c2a81ac',  # noqa:E501
     'www.wikidata.org',
     'Q474472$dcf39f47-4275-6529-96f5-94808c2a81ac'),
    ('https://commons.wikimedia.org/entity/statement/M80857538-e33a73d7-4567-a029-a6e6-14eb3bab8a65',  # noqa:E501
     'commons.wikimedia.org',
     'M80857538$e33a73d7-4567-a029-a6e6-14eb3bab8a65')
])
def test_statement_id_from_uri(uri: str, wiki: str, statement_id: str):
    assert ranker.statement_id_from_uri(uri, wiki) == statement_id


@pytest.mark.parametrize('statement_id, entity_id', [
    ('Q1$123', 'Q1'),
    ('p1$123', 'P1'),
    ('L1-S1$123', 'L1-S1'),
])
def test_entity_id_from_statement_id(statement_id: str, entity_id: str):
    assert ranker.entity_id_from_statement_id(statement_id) == entity_id


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


def test_parse_statement_ids_with_ranks():
    input = '''
Q1$123|normal
Q2$123|deprecated
Q1$456\tpreferred
q2$456\tnormal
P3$123|preferred
'''.strip()
    assert ranker.parse_statement_ids_with_ranks(input) == {
        'Q1': {'Q1$123': 'normal', 'Q1$456': 'preferred'},
        'Q2': {'Q2$123': 'deprecated', 'q2$456': 'normal'},
        'P3': {'P3$123': 'preferred'},
    }


def test_get_entities():
    class FakeSession:
        def get(self, ids, **kwargs):
            assert len(ids) <= 50
            return {'entities': {id: f'entity {id}' for id in ids}}

    entity_ids = [f'Q{id}' for id in range(1, 120)]
    entities = ranker.get_entities(FakeSession(), entity_ids)
    assert entities == {id: f'entity {id}' for id in entity_ids}


@pytest.mark.parametrize('entity, expected_statements', [
    pytest.param({'type': 'item', 'claims': 'X'}, 'X', id='item'),
    pytest.param({'type': 'property', 'claims': 'X'}, 'X', id='property'),
    pytest.param({'type': 'lexeme', 'claims': 'X'}, 'X', id='lexeme'),
    pytest.param({'type': 'sense', 'claims': 'X'}, 'X', id='sense'),
    pytest.param({'type': 'form', 'claims': 'X'}, 'X', id='form'),
    pytest.param({'claims': 'X'}, 'X', id='sense or form (T272804)'),
    pytest.param({'type': 'mediainfo', 'statements': ''}, '', id='mediainfo'),
    pytest.param({'type': 'mediainfo', 'statements': []}, {}, id='T222159'),
])
def test_entity_statements(entity: dict, expected_statements):
    statements = ranker.entity_statements(entity)
    assert expected_statements == statements


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


def test_statements_edit_rank():
    unselected_statement = {'id': 'Y', 'rank': 'normal'}
    unedited_statement = {'id': 'a', 'rank': 'preferred'}
    edited_statement = {'id': 'b', 'rank': 'normal'}
    commands = {'a': 'preferred', 'b': 'preferred'}
    statements = {
        'P1': [
            unselected_statement,
            unedited_statement,
            edited_statement,
        ],
    }

    statements, edited_statements = ranker.statements_edit_rank(
        commands,
        statements,
    )

    assert edited_statements == 1
    assert 'P1' in statements
    assert edited_statement in statements['P1']
    assert edited_statement['rank'] == 'preferred'
    assert unedited_statement['rank'] == 'preferred'
    assert unselected_statement['rank'] == 'normal'


@pytest.mark.parametrize('s, expected', [
    (None, None),
    ('', ''),
    (' ', ''),
    (' abc ', 'abc'),
    ('abc', 'abc'),
])
def test_str_strip_optional(s: Optional[str], expected: Optional[str]):
    assert ranker.str_strip_optional(s) == expected


@pytest.mark.parametrize('edited_statements, rank, custom_summary, expected', [
    (1, 'preferred', None, 'Set rank of 1 statement to preferred'),
    (2, 'deprecated', '', 'Set rank of 2 statements to deprecated'),
    (3, 'normal', 'custom', 'Set rank of 3 statements to normal: custom'),
    (4, 'preferred', ' ', 'Set rank of 4 statements to preferred'),
])
def test_get_summary_set_rank(edited_statements: int,
                              rank: str,
                              custom_summary: Optional[str],
                              expected: str):
    assert expected == ranker.get_summary_set_rank(edited_statements,
                                                   rank,
                                                   custom_summary)


@pytest.mark.parametrize('edited_statements, custom_summary, expected', [
    (1, None, 'Incremented rank of 1 statement'),
    (2, 'custom', 'Incremented rank of 2 statements: custom'),
    (3, '', 'Incremented rank of 3 statements'),
    (4, ' ', 'Incremented rank of 4 statements'),
])
def test_get_summary_increment_rank(edited_statements: int,
                                    custom_summary: Optional[str],
                                    expected: str):
    assert expected == ranker.get_summary_increment_rank(edited_statements,
                                                         custom_summary)


@pytest.mark.parametrize('edited_statements, custom_summary, expected', [
    (1, None, 'Edited rank of 1 statement'),
    (2, 'custom', 'Edited rank of 2 statements: custom'),
    (3, '', 'Edited rank of 3 statements'),
    (4, ' ', 'Edited rank of 4 statements'),
])
def test_get_summary_edit_rank(edited_statements: int,
                               custom_summary: Optional[str],
                               expected: str):
    assert expected == ranker.get_summary_edit_rank(edited_statements,
                                                    custom_summary)
