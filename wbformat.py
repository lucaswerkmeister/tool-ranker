from bs4 import BeautifulSoup
import cachetools
from collections.abc import Collection
import json
from markupsafe import Markup
import mwapi  # type: ignore
import threading
from typing import List, Tuple


format_value_cache = cachetools.TTLCache(maxsize=1000,  # type: ignore
                                         ttl=60 * 60)
format_value_cache_lock = threading.RLock()


def format_value_key(session: mwapi.Session,
                     lang: str,
                     property_id: str,
                     value: dict) -> Tuple[str, str, str, str]:
    return (session.host, lang, property_id, json.dumps(value))


@cachetools.cached(cache=format_value_cache,
                   key=format_value_key,
                   lock=format_value_cache_lock)
def format_value(session: mwapi.Session,
                 lang: str,
                 property_id: str,
                 value: dict) -> Markup:
    response = session.get(
        action='wbformatvalue',
        datavalue=json.dumps(value),
        property=property_id,
        generate='text/html',
        uselang=lang,
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
                      lang: str,
                      entity_id: str) -> Tuple[str, str, str]:
    return (session.host, lang, entity_id)


@cachetools.cached(cache=format_entity_cache,
                   key=format_entity_key,
                   lock=format_entity_cache_lock)
def format_entity(session: mwapi.Session,
                  lang: str,
                  entity_id: str) -> Markup:
    response = session.get(
        action='wbformatentities',
        ids=[entity_id],
        uselang=lang,
        formatversion=2,
    )
    return Markup(response['wbformatentities'][entity_id])


def prefetch_entities(session: mwapi.Session,
                      lang: str,
                      entity_ids: Collection[str]):
    with format_entity_cache_lock:
        entity_id_chunks: List[List[str]] = []
        for entity_id in entity_ids:
            key = format_entity_key(session, lang, entity_id)
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
            uselang=lang,
            formatversion=2,
        )['wbformatentities']
        with format_entity_cache_lock:
            for entity_id in response:
                key = format_entity_key(session, lang, entity_id)
                value = Markup(response[entity_id])
                format_entity_cache[key] = value
