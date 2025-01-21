from typing import Collection, cast
from SPARQLWrapper import SPARQLWrapper, JSON  # type: ignore


_query_services = {
    'www.wikidata.org': (
        'query.wikidata.org',
        'wdqs',
    ),
}


def query_wiki(wiki: str, query: str, user_agent: str) -> dict:
    query_service = _query_services[wiki][0]
    sparql = SPARQLWrapper(f'https://{query_service}/sparql', agent=user_agent)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    return cast(dict, sparql.query().convert())


def wikis_with_query_service() -> Collection[str]:
    return _query_services.keys()


def query_service_id(wiki: str) -> str:
    """Return a short identifier of the query service, for message keys."""
    return _query_services[wiki][1]


def query_service_url(wiki: str) -> str:
    query_service = _query_services[wiki][0]
    return f'https://{query_service}/'
