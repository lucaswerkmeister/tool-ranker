import cachetools
import flask
import json
import mwapi  # type: ignore
import threading
from typing import AbstractSet, List, Tuple


def format_value(session: mwapi.Session,
                 property_id: str,
                 value: dict) -> flask.Markup:
    response = session.get(action='wbformatvalue',
                           datavalue=json.dumps(value),
                           property=property_id,
                           generate='text/plain')
    return flask.Markup.escape(response['result'])


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
                  entity_id: str) -> flask.Markup:
    response = session.get(action='wbformatentities',
                           ids=[entity_id],
                           formatversion=2)
    return flask.Markup(response['wbformatentities'][entity_id])


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
            response = session.get(action='wbformatentities',
                                   ids=entity_id_chunk,
                                   formatversion=2)['wbformatentities']
            for entity_id in response:
                key = format_entity_key(session, entity_id)
                value = flask.Markup(response[entity_id])
                format_entity_cache[key] = value
