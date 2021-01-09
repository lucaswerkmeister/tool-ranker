import cachetools
import flask
import json
import mwapi  # type: ignore
import threading
from typing import Tuple


def format_value(session: mwapi.Session,
                 property_id: str,
                 value: dict) -> flask.Markup:
    response = session.get(action='wbformatvalue',
                           datavalue=json.dumps(value),
                           property=property_id,
                           generate='text/plain')
    return flask.Markup.escape(response['result'])


FormatPropertyCache = cachetools.TTLCache[Tuple[str, str], flask.Markup]
format_property_cache: FormatPropertyCache = cachetools.TTLCache(maxsize=1000,
                                                                 ttl=60 * 60)
format_property_cache_lock = threading.RLock()


def format_property_key(session: mwapi.Session,
                        property_id: str) -> Tuple[str, str]:
    return (session.host, property_id)


@cachetools.cached(cache=format_property_cache,  # type: ignore
                   key=format_property_key,
                   lock=format_property_cache_lock)
def format_property(session: mwapi.Session,
                    property_id: str) -> flask.Markup:
    response = session.get(action='wbformatentities',
                           ids=[property_id],
                           formatversion=2)
    return flask.Markup(response['wbformatentities'][property_id])
