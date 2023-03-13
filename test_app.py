import flask
import pytest
from typing import Optional

import app as ranker
import query_service

import test_query_service


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


@pytest.mark.parametrize('wiki, has_query_service', [
    ('www.wikidata.org', True),
    ('commons.wikimedia.org', False),
    ('test.wikidata.org', False),
    ('test-commons.wikimedia.org', False),
])
def test_has_query_service(wiki: str, has_query_service: bool):
    assert ranker.has_query_service(wiki) == has_query_service


@pytest.mark.parametrize('wiki, property_id', [
    ('www.wikidata.org', 'P7452'),
    ('commons.wikimedia.org', 'P7452'),
    ('test.wikidata.org', None),
    ('test-commons.wikimedia.org', None),
])
def test_wiki_reason_preferred_property(wiki: str, property_id: Optional[str]):
    assert ranker.wiki_reason_preferred_property(wiki) == property_id


@pytest.mark.parametrize('wiki, property_id', [
    ('www.wikidata.org', 'P2241'),
    ('commons.wikimedia.org', 'P2241'),
    ('test.wikidata.org', None),
    ('test-commons.wikimedia.org', None),
])
def test_wiki_reason_deprecated_property(wiki: str, property_id: Optional[str]):  # noqa: E501
    assert ranker.wiki_reason_deprecated_property(wiki) == property_id


def test_index_redirect(client):
    response = client.post('/',
                           data={'wiki': 'www.wikidata.org',
                                 'entity_id': 'Q4115189',
                                 'property_id': 'P361'})
    expected_redirect = '/edit/www.wikidata.org/Q4115189/P361/'
    assert response.headers['location'] == expected_redirect


def test_index_redirect_mediainfo(client):
    response = client.post('/',
                           data={'wiki': 'commons.wikimedia.org',
                                 'entity_id': 'File:DSC 0484 2-01.jpg',
                                 'property_id': 'P180'})
    expected_redirect = '/edit/commons.wikimedia.org/M79869096/P180/'
    assert response.headers['location'] == expected_redirect


@pytest.mark.filterwarnings('ignore::bs4.MarkupResemblesLocatorWarning')
def test_format_value_escapes_html():
    value = {'value': '<script>alert("!Mediengruppe Bitnik");</script>',
             'type': 'string'}
    expected = flask.Markup(r'&lt;script&gt;alert("!Mediengruppe'
                            r' Bitnik");&lt;/script&gt;')
    assert ranker.format_value('test.wikidata.org', 'P95', value) == expected


@pytest.mark.parametrize('uri, wiki, item_id', [
    ('http://www.wikidata.org/entity/Q1', 'www.wikidata.org', 'Q1'),
    ('http://www.wikidata.org/entity/Q2', 'commons.wikimedia.org', 'Q2'),
    ('http://test.wikidata.org/entity/Q3', 'test.wikidata.org', 'Q3'),
    ('http://test.wikidata.org/entity/Q4', 'test-commons.wikimedia.org', 'Q4'),
])
def test_item_id_from_uri(uri: str, wiki: str, item_id: str):
    assert ranker.item_id_from_uri(uri, wiki) == item_id


@pytest.mark.parametrize('uri, wiki, statement_id', [
    ('http://www.wikidata.org/entity/statement/Q474472-dcf39f47-4275-6529-96f5-94808c2a81ac',  # noqa:E501
     'www.wikidata.org',
     'Q474472$dcf39f47-4275-6529-96f5-94808c2a81ac'),
    ('http://www.wikidata.org/entity/statement/L1-S1-b5a7d210-4269-b5ec-68ea-9d56b8a73f46',  # noqa:E501
     'www.wikidata.org',
     'L1-S1$b5a7d210-4269-b5ec-68ea-9d56b8a73f46'),
    ('http://www.wikidata.org/entity/statement/L1-F1-0fbbfd13-4840-be9b-fe4e-66af032ff452',  # noqa:E501
     'www.wikidata.org',
     'L1-F1$0fbbfd13-4840-be9b-fe4e-66af032ff452'),
    ('https://commons.wikimedia.org/entity/statement/M80857538-e33a73d7-4567-a029-a6e6-14eb3bab8a65',  # noqa:E501
     'commons.wikimedia.org',
     'M80857538$e33a73d7-4567-a029-a6e6-14eb3bab8a65')
])
def test_statement_id_from_uri(uri: str, wiki: str, statement_id: str):
    assert ranker.statement_id_from_uri(uri, wiki) == statement_id


@pytest.mark.parametrize('uri, rank', [
    ('http://wikiba.se/ontology#DeprecatedRank', 'deprecated'),
    ('http://wikiba.se/ontology#NormalRank', 'normal'),
    ('http://wikiba.se/ontology#PreferredRank', 'preferred'),
])
def test_rank_from_uri(uri: str, rank: str):
    assert ranker.rank_from_uri(uri) == rank


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


def test_query_statement_ids(monkeypatch):
    def query_wiki(wiki: str, query: str, user_agent: str) -> dict:
        assert wiki == test_query_service.test_wiki
        assert query == test_query_service.test_query
        return test_query_service.test_query_results

    # monkeypatch original and imported function to support either import style
    monkeypatch.setattr(ranker, 'query_wiki', query_wiki)
    monkeypatch.setattr(query_service, 'query_wiki', query_wiki)

    wiki = test_query_service.test_wiki
    query = test_query_service.test_query
    assert ranker.query_statement_ids(wiki, query) == {
        'Q474472': ['Q474472$dcf39f47-4275-6529-96f5-94808c2a81ac'],
        'Q3841190': ['Q3841190$dbcf6be8-41c0-5955-d618-2d06ab241344'],
    }


def test_parse_statement_ids_with_ranks_and_reasons():
    input = '''
Q1$123|normal
Q2$123|deprecated|Q123
Q1$456\tpreferred\tQ456
q2$456\tnormal|Q789
P3$123|preferred|
'''.strip()
    assert ranker.parse_statement_ids_with_ranks_and_reasons(input) == {
        'Q1': {'Q1$123': ('normal', ''), 'Q1$456': ('preferred', 'Q456')},
        'Q2': {'Q2$123': ('deprecated', 'Q123'), 'q2$456': ('normal', 'Q789')},
        'P3': {'P3$123': ('preferred', '')},
    }


def test_query_statement_ids_with_ranks_and_reasons(monkeypatch):
    test_wiki = 'www.wikidata.org'
    test_query = '''
SELECT
    ?statement
    ?rank
    ?reason
    ?reasonForPreferredRank
    ?reasonForDeprecatedRank
WHERE {
  hint:Query hint:optimizer "None".
  {
    SELECT ?statement (1 AS ?num) WHERE {
      wd:Q474472 p:P18 ?statement.
    }
  } UNION {
    SELECT ?statement (wd:Q71533355 AS ?reason) ?num WHERE {
      VALUES (?item ?num) {
        (wd:Q3841190 2)
        (wd:Q843864 3)
      }
      ?item p:P18 ?statement.
    }
  } UNION {
    SELECT
        ?statement
        (wd:Q71536040 AS ?reasonForPreferredRank)
        (wd:Q41755623 AS ?reasonForDeprecatedRank)
        ?num
    WHERE {
      VALUES (?rank ?num) {
        (wikibase:PreferredRank 4)
        (wikibase:DeprecatedRank 5)
      }
      wd:Q12567 p:P18 ?statement.
      ?statement wikibase:rank ?rank.
    }
  }
  ?statement wikibase:rank ?rank.
}
ORDER BY ?num
'''.strip()
    test_query_results = {
        'head': {'vars': [
            'statement',
            'rank',
            'reason',
            'reasonForPreferredRank',
            'reasonForDeprecatedRank',
        ]},
        'results': {'bindings': [
            {
                'rank': {
                    'type': 'uri',
                    'value': 'http://wikiba.se/ontology#NormalRank',
                },
                'statement': {
                    'type': 'uri',
                    'value': 'http://www.wikidata.org/entity/statement/Q474472-dcf39f47-4275-6529-96f5-94808c2a81ac',  # noqa: E501
                },
            },
            {
                'rank': {
                    'type': 'uri',
                    'value': 'http://wikiba.se/ontology#NormalRank',
                },
                'reason': {
                    'type': 'uri',
                    'value': 'http://www.wikidata.org/entity/Q71533355',
                },
                'statement': {
                    'type': 'uri',
                    'value': 'http://www.wikidata.org/entity/statement/Q3841190-dbcf6be8-41c0-5955-d618-2d06ab241344',  # noqa: E501
                },
            },
            {
                'rank': {
                    'type': 'uri',
                    'value': 'http://wikiba.se/ontology#NormalRank',
                },
                'reason': {
                    'type': 'uri',
                    'value': 'http://www.wikidata.org/entity/Q71533355',
                },
                'statement': {
                    'type': 'uri',
                    'value': 'http://www.wikidata.org/entity/statement/Q843864-27BF8D25-B1A9-4488-94BF-9564EE2A5776',  # noqa: E501
                },
            },
            {
                'rank': {
                    'type': 'uri',
                    'value': 'http://wikiba.se/ontology#PreferredRank',
                },
                'reasonForDeprecatedRank': {
                    'type': 'uri',
                    'value': 'http://www.wikidata.org/entity/Q41755623',
                },
                'reasonForPreferredRank': {
                    'type': 'uri',
                    'value': 'http://www.wikidata.org/entity/Q71536040',
                },
                'statement': {
                    'type': 'uri',
                    'value': 'http://www.wikidata.org/entity/statement/Q12567-0688176e-463d-ec87-4a0e-5ef10e47112a',  # noqa: E501
                },
            },
            {
                'rank': {
                    'type': 'uri',
                    'value': 'http://wikiba.se/ontology#DeprecatedRank',
                },
                'reasonForDeprecatedRank': {
                    'type': 'uri',
                    'value': 'http://www.wikidata.org/entity/Q41755623',
                },
                'reasonForPreferredRank': {
                    'type': 'uri',
                    'value': 'http://www.wikidata.org/entity/Q71536040',
                },
                'statement': {
                    'type': 'uri',
                    'value': 'http://www.wikidata.org/entity/statement/Q12567-cfae68c3-49ab-99be-85f5-d99272d780d1',  # noqa: E501
                },
            },
        ]},
    }

    def query_wiki(wiki: str, query: str, user_agent: str) -> dict:
        assert wiki == test_wiki
        assert query == test_query
        return test_query_results

    # monkeypatch original and imported function to support either import style
    monkeypatch.setattr(ranker, 'query_wiki', query_wiki)
    monkeypatch.setattr(query_service, 'query_wiki', query_wiki)

    actual = ranker.query_statement_ids_with_ranks_and_reasons(
        test_wiki,
        test_query,
    )
    assert actual == {
        'Q474472': {
            'Q474472$dcf39f47-4275-6529-96f5-94808c2a81ac': ('normal', ''),
        },
        'Q3841190': {
            'Q3841190$dbcf6be8-41c0-5955-d618-2d06ab241344': ('normal', 'Q71533355'),  # noqa: E501
        },
        'Q843864': {
            'Q843864$27BF8D25-B1A9-4488-94BF-9564EE2A5776': ('normal', 'Q71533355'),  # noqa: E501
        },
        'Q12567': {
            'Q12567$0688176e-463d-ec87-4a0e-5ef10e47112a': ('preferred', 'Q71536040'),  # noqa: E501
            'Q12567$cfae68c3-49ab-99be-85f5-d99272d780d1': ('deprecated', 'Q41755623'),  # noqa: E501
        },
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


def test_statements_set_rank_to():
    def reason():
        return {'qualifiers': {'P2241': ['reason for deprecated rank']}}
    unrelated_statement = {'id': 'X', 'rank': 'normal', **reason()}
    unselected_statement = {'id': 'Y', 'rank': 'normal', **reason()}
    unedited_statement = {'id': 'a', 'rank': 'preferred', **reason()}
    edited_statement = {'id': 'b', 'rank': 'normal', **reason()}
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
    wiki = 'www.wikidata.org'

    statements, edited_statements = ranker.statements_set_rank_to(
        statement_ids,
        rank,
        statements,
        wiki,
        'reason',
    )

    assert edited_statements == 1
    assert property_id in statements
    assert edited_statement in statements[property_id]
    assert edited_statement['rank'] == 'preferred'
    assert 'P2241' not in edited_statement['qualifiers']
    assert edited_statement['qualifiers']['P7452'][0]\
        ['datavalue']['value']['id'] == 'reason'  # noqa: E211
    assert unedited_statement['rank'] == 'preferred'
    assert unedited_statement['qualifiers']['P2241']
    assert 'P7452' not in unedited_statement['qualifiers']
    assert unselected_statement['rank'] == 'normal'
    assert unselected_statement['qualifiers']['P2241']
    assert 'P7452' not in unselected_statement['qualifiers']
    assert unrelated_statement['rank'] == 'normal'
    assert unrelated_statement['qualifiers']['P2241']
    assert 'P7452' not in unrelated_statement['qualifiers']
    assert statements == {property_id: [edited_statement]}


@pytest.mark.parametrize('empty_reason', [None, ''])
def test_statements_increment_rank(empty_reason):
    def reason():
        return {'qualifiers': {'P2241': ['reason for deprecated rank']}}
    unrelated_statement = {'id': 'X', 'rank': 'normal', **reason()}
    unselected_statement = {'id': 'Y', 'rank': 'normal', **reason()}
    unedited_statement = {'id': 'a', 'rank': 'preferred', **reason()}
    edited_statement = {'id': 'b', 'rank': 'normal', **reason()}
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
    wiki = 'www.wikidata.org'

    statements, edited_statements = ranker.statements_increment_rank(
        statement_ids,
        statements,
        wiki,
        empty_reason,
    )

    assert edited_statements == 1
    assert property_id in statements
    assert edited_statement in statements[property_id]
    assert edited_statement['rank'] == 'preferred'
    assert not edited_statement['qualifiers']
    assert unedited_statement['rank'] == 'preferred'
    assert unedited_statement['qualifiers']['P2241']
    assert unselected_statement['rank'] == 'normal'
    assert unselected_statement['qualifiers']['P2241']
    assert unrelated_statement['rank'] == 'normal'
    assert unrelated_statement['qualifiers']['P2241']
    assert statements == {property_id: [edited_statement]}


def test_statements_increment_rank_unsupported():
    statement_ids = {'a'}
    statements = {'P1': [{'id': 'a', 'rank': 'normal'}]}
    wiki = 'www.wikidata.org'
    reason = 'reason'

    with pytest.raises(Exception, match='not supported'):
        ranker.statements_increment_rank(
            statement_ids,
            statements,
            wiki,
            reason,
        )


def test_statements_edit_rank():
    def reason():
        return {'qualifiers': {'P2241': ['reason for deprecated rank']}}
    unselected_statement = {'id': 'Y', 'rank': 'normal', **reason()}
    unedited_statement = {'id': 'a', 'rank': 'preferred', **reason()}
    edited_statement = {'id': 'b', 'rank': 'normal', **reason()}
    commands = {'a': ('preferred', 'reason A'), 'b': ('preferred', 'reason B')}
    statements = {
        'P1': [
            unselected_statement,
            unedited_statement,
            edited_statement,
        ],
    }
    wiki = 'www.wikidata.org'

    statements, edited_statements = ranker.statements_edit_rank(
        commands,
        statements,
        wiki,
    )

    assert edited_statements == 1
    assert 'P1' in statements
    assert edited_statement in statements['P1']
    assert edited_statement['rank'] == 'preferred'
    assert 'P2241' not in edited_statement['qualifiers']
    assert edited_statement['qualifiers']['P7452'][0]\
        ['datavalue']['value']['id'] == 'reason B'  # noqa: E211
    assert unedited_statement['rank'] == 'preferred'
    assert unedited_statement['qualifiers']['P2241']
    assert 'P7452' not in unedited_statement['qualifiers']
    assert unselected_statement['rank'] == 'normal'
    assert unselected_statement['qualifiers']['P2241']
    assert 'P7452' not in unselected_statement['qualifiers']


@pytest.mark.parametrize('statement, wiki, expected', [
    (  # Wikidata
        {'qualifiers': {
            'P7452': ['preferred reason A', 'preferred reason B'],
            'P2241': ['deprecated reason'],
            'P642': ['unrelated qualifier'],
        }, 'mainsnak': 'whatever'},
        'www.wikidata.org',
        {'qualifiers': {
            'P642': ['unrelated qualifier'],
        }, 'mainsnak': 'whatever'},
    ),
    (  # Commons (same as Wikidata except for the wiki)
        {'qualifiers': {
            'P7452': ['preferred reason A', 'preferred reason B'],
            'P2241': ['deprecated reason'],
            'P642': ['unrelated qualifier'],
        }, 'mainsnak': 'whatever'},
        'commons.wikimedia.org',
        {'qualifiers': {
            'P642': ['unrelated qualifier'],
        }, 'mainsnak': 'whatever'},
    ),
    (  # Test Wikidata (same statement as Wikidata but should have no effect)
        {'qualifiers': {
            'P7452': ['preferred reason A', 'preferred reason B'],
            'P2241': ['deprecated reason'],
            'P642': ['unrelated qualifier'],
        }, 'mainsnak': 'whatever'},
        'test.wikidata.org',
        {'qualifiers': {
            'P7452': ['preferred reason A', 'preferred reason B'],
            'P2241': ['deprecated reason'],
            'P642': ['unrelated qualifier'],
        }, 'mainsnak': 'whatever'},
    ),
    (  # Test Commons (same as Test Wikidata)
        {'qualifiers': {
            'P7452': ['preferred reason A', 'preferred reason B'],
            'P2241': ['deprecated reason'],
            'P642': ['unrelated qualifier'],
        }, 'mainsnak': 'whatever'},
        'test-commons.wikimedia.org',
        {'qualifiers': {
            'P7452': ['preferred reason A', 'preferred reason B'],
            'P2241': ['deprecated reason'],
            'P642': ['unrelated qualifier'],
        }, 'mainsnak': 'whatever'},
    ),
    (  # statement without qualifiers
        {},
        'www.wikidata.org',
        {},
    ),
])
def test_statement_remove_reasons(statement, wiki, expected):
    ranker.statement_remove_reasons(statement, wiki)
    assert statement == expected


@pytest.mark.parametrize('statement, rank, wiki, expected', [
    (
        {'id': 'X'},
        'preferred',
        'www.wikidata.org',
        {'id': 'X', 'qualifiers': {'P7452': [{
            'snaktype': 'value',
            'property': 'P7452',
            'datatype': 'wikibase-item',
            'datavalue': {
                'type': 'wikibase-entityid',
                'value': {
                    'entity-type': 'item',
                    'id': 'reason',
                },
            },
        }]}},
    ),
    (
        {'id': 'Y', 'qualifiers': {'P642': ['existing-qualifier']}},
        'deprecated',
        'commons.wikimedia.org',
        {'id': 'Y', 'qualifiers': {
            'P642': ['existing-qualifier'],
            'P2241': [{
                'snaktype': 'value',
                'property': 'P2241',
                'datatype': 'wikibase-item',
                'datavalue': {
                    'type': 'wikibase-entityid',
                    'value': {
                        'entity-type': 'item',
                        'id': 'reason',
                    },
                },
            }],
        }},
    ),
])
def test_statement_set_reason(statement, rank, wiki, expected):
    ranker.statement_set_reason(statement, rank, wiki, 'reason')
    assert statement == expected


@pytest.mark.parametrize('reason', [None, ''])
def test_statement_set_reason_noop(reason):
    statement = {'id': 'X'}
    rank = 'preferred'
    wiki = 'www.wikidata.org'

    ranker.statement_set_reason(statement, rank, wiki, reason)
    assert statement == {'id': 'X'}


@pytest.mark.parametrize('rank, wiki', [
    ('preferred', 'test.wikidata.org'),
    ('normal', 'test.wikidata.org'),
    ('deprecated', 'test.wikidata.org'),
    ('preferred', 'test-commons.wikimedia.org'),
    ('normal', 'test-commons.wikimedia.org'),
    ('deprecated', 'test-commons.wikimedia.org'),
    ('normal', 'www.wikidata.org'),
    ('normal', 'commons.wikimedia.org'),
])
def test_statement_set_reason_unsupported(rank, wiki):
    with pytest.raises(Exception, match='Cannot set a reason'):
        ranker.statement_set_reason({}, rank, wiki, 'reason')


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
    wiki = 'www.wikidata.org'
    reason = ''
    assert expected == ranker.get_summary_set_rank(edited_statements,
                                                   rank,
                                                   wiki,
                                                   reason,
                                                   custom_summary)


@pytest.mark.parametrize('wiki, reason, expected', [
    ('www.wikidata.org', 'Q1', 'reason: [[Q1]]'),
    ('commons.wikimedia.org', 'Q2', 'reason: [[d:Special:EntityPage/Q2]]'),
    ('test.wikidata.org', 'Q3', 'reason: [[Q3]]'),
    ('test-commons.wikimedia.org', 'Q4', 'reason: [[testwikidata:Special:EntityPage/Q4]]'),  # noqa: E501
])
def test_get_summary_set_rank_reason(wiki: str, reason: str, expected: str):
    edited_statements = 1
    rank = 'preferred'
    custom_summary = None
    expected = 'Set rank of 1 statement to preferred (' + expected + ')'
    assert expected == ranker.get_summary_set_rank(edited_statements,
                                                   rank,
                                                   wiki,
                                                   reason,
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
