from typing import Collection
from SPARQLWrapper import SPARQLWrapper, JSON  # type: ignore


_query_services = {
    'www.wikidata.org': (
        'query.wikidata.org',
        'Wikidata Query Service',
    ),
    'commons.wikimedia.org': (
        'wcqs-beta.wmflabs.org',
        'Wikimedia Commons Query Service',
    ),
}


def query_wiki(wiki: str, query: str, user_agent: str) -> dict:
    query_service = _query_services[wiki][0]
    sparql = SPARQLWrapper(f'https://{query_service}/sparql', agent=user_agent)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    return sparql.query().convert()


def wikis_with_query_service() -> Collection[str]:
    return _query_services.keys()


def query_service_name(wiki: str) -> str:
    return _query_services[wiki][1]


def query_service_url(wiki: str) -> str:
    query_service = _query_services[wiki][0]
    return f'https://{query_service}/'