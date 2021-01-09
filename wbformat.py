import flask
import json
import mwapi  # type: ignore


def format_value(session: mwapi.Session,
                 property_id: str,
                 value: dict) -> flask.Markup:
    response = session.get(action='wbformatvalue',
                           datavalue=json.dumps(value),
                           property=property_id,
                           generate='text/plain')
    return flask.Markup.escape(response['result'])
