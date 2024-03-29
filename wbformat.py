from bs4 import BeautifulSoup
import cachetools
import json
from markupsafe import Markup
import mwapi  # type: ignore
import threading
from typing import AbstractSet, List, Tuple


def format_value(session: mwapi.Session,
                 property_id: str,
                 value: dict) -> Markup:
    response = session.get(
        action='wbformatvalue',
        datavalue=json.dumps(value),
        property=property_id,
        generate='text/html',
        # force English, all the tool is in English
        # and we don’t split the cache by language
        uselang='en',
    )
    html = BeautifulSoup(response['result'], features='html.parser')
    # turn links into spans – clicking the value should toggle the checkbox,
    # and also the hrefs returned by Wikibase are relative anyways (T218646)
    for link in html.find_all('a'):
        link.name = 'span'
        del link['href']
    return Markup(html)


format_entity_cache = cachetools.TTLCache(maxsize=1000,  # type: ignore
                                          ttl=60 * 60)
format_entity_cache_lock = threading.RLock()


def format_entity_key(session: mwapi.Session,
                      entity_id: str) -> Tuple[str, str]:
    return (session.host, entity_id)


@cachetools.cached(cache=format_entity_cache,
                   key=format_entity_key,
                   lock=format_entity_cache_lock)
def format_entity(session: mwapi.Session,
                  entity_id: str) -> Markup:
    response = session.get(
        action='wbformatentities',
        ids=[entity_id],
        # force English (see above)
        uselang='en',
        formatversion=2,
    )
    return Markup(response['wbformatentities'][entity_id])


def prefetch_entities(session: mwapi.Session,
                      entity_ids: AbstractSet[str]):
    with format_entity_cache_lock:
        entity_id_chunks: List[List[str]] = []
        for entity_id in entity_ids:
            key = format_entity_key(session, entity_id)
            if key in format_entity_cache:
                continue
            if len(entity_id_chunks) == 0:
                entity_id_chunks.append([entity_id])
            else:
                last_chunk = entity_id_chunks[-1]
                if len(last_chunk) >= 50:
                    entity_id_chunks.append([entity_id])
                else:
                    last_chunk.append(entity_id)
        for entity_id_chunk in entity_id_chunks:
            response = session.get(
                action='wbformatentities',
                ids=entity_id_chunk,
                # force English (see above)
                uselang='en',
                formatversion=2,
            )['wbformatentities']
            for entity_id in response:
                key = format_entity_key(session, entity_id)
                value = Markup(response[entity_id])
                format_entity_cache[key] = value
