import pytest  # type: ignore

import query_service


test_wiki = "www.wikidata.org"
test_query = """
SELECT ?item ?statement ?value WHERE {
  VALUES (?item ?num) {
    (wd:Q474472 1)
    (wd:Q3841190 2)
  }
  ?item p:P18 ?statement.
  ?statement ps:P18 ?value.
}
ORDER BY ?num
""".strip()
test_query_results = {
    'head': {'vars': ['item', 'statement', 'value']},
    'results': {'bindings': [
        {
            'item': {
                'type': 'uri',
                'value': 'http://www.wikidata.org/entity/Q474472'
            },
            'statement': {
                'type': 'uri',
                'value': 'http://www.wikidata.org/entity/statement/Q474472-dcf39f47-4275-6529-96f5-94808c2a81ac'  # noqa:E501
            },
            'value': {
                'type': 'uri',
                'value': 'http://commons.wikimedia.org/wiki/Special:FilePath/Earth%20as%20a%20%22Pale%20Blue%20Dot%22%20photographed%20by%20Voyager%201%20-%2019900606.tif'  # noqa:E501
            }
        },
        {
            'item': {
                'type': 'uri',
                'value': 'http://www.wikidata.org/entity/Q3841190'
            },
            'statement': {
                'type': 'uri',
                'value': 'http://www.wikidata.org/entity/statement/Q3841190-dbcf6be8-41c0-5955-d618-2d06ab241344'  # noqa:E501
            },
            'value': {
                'type': 'uri',
                'value': 'http://commons.wikimedia.org/wiki/Special:FilePath/Black%20hole%20-%20Messier%2087.jpg'  # noqa:E501
            }
        },
    ]},
}


def test_query_wiki():
    user_agent = ('ranker-test (https://ranker.toolforge.org/; '
                  'ranker@lucaswerkmeister.de)')
    results = query_service.query_wiki(test_wiki, test_query, user_agent)
    assert results == test_query_results


def test_wikis_with_query_service():
    assert query_service.wikis_with_query_service() == {
        'www.wikidata.org',
        'commons.wikimedia.org',
    }


@pytest.mark.parametrize('wiki, expected', [
    ('www.wikidata.org', 'Wikidata Query Service'),
    ('commons.wikimedia.org', 'Wikimedia Commons Query Service'),
])
def test_query_service_name(wiki: str, expected: str):
    assert query_service.query_service_name(wiki) == expected


@pytest.mark.parametrize('wiki, expected', [
    ('www.wikidata.org', 'https://query.wikidata.org/'),
    ('commons.wikimedia.org', 'https://wcqs-beta.wmflabs.org/'),
])
def test_query_service_url(wiki: str, expected: str):
    assert query_service.query_service_url(wiki) == expected
