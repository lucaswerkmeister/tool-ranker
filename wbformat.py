import cachetools
import flask
import json
import mwapi  # type: ignore
import threading
from typing import List, Set, Tuple


def format_value(session: mwapi.Session,
                 property_id: str,
                 value: dict) -> flask.Markup:
    response = session.get(action='wbformatvalue',
                           datavalue=json.dumps(value),
                           property=property_id,
                           generate='text/plain')
    return flask.Markup.escape(response['result'])


format_property_cache = cachetools.TTLCache(maxsize=1000,  # type: ignore
                                            ttl=60 * 60)
format_property_cache_lock = threading.RLock()


def format_property_key(session: mwapi.Session,
                        property_id: str) -> Tuple[str, str]:
    return (session.host, property_id)


@cachetools.cached(cache=format_property_cache,
                   key=format_property_key,
                   lock=format_property_cache_lock)
def format_property(session: mwapi.Session,
                    property_id: str) -> flask.Markup:
    response = session.get(action='wbformatentities',
                           ids=[property_id],
                           formatversion=2)
    return flask.Markup(response['wbformatentities'][property_id])


def prefetch_properties(session: mwapi.Session,
                        property_ids: Set[str]):
    with format_property_cache_lock:
        property_id_chunks: List[List[str]] = []
        for property_id in property_ids:
            key = format_property_key(session, property_id)
            if key in format_property_cache:
                continue
            if len(property_id_chunks) == 0:
                property_id_chunks.append([property_id])
            else:
                last_chunk = property_id_chunks[-1]
                if len(last_chunk) >= 50:
                    property_id_chunks.append([property_id])
                else:
                    last_chunk.append(property_id)
        for property_id_chunk in property_id_chunks:
            response = session.get(action='wbformatentities',
                                   ids=property_id_chunk,
                                   formatversion=2)['wbformatentities']
            for property_id in response:
                key = format_property_key(session, property_id)
                value = flask.Markup(response[property_id])
                format_property_cache[key] = value
