# -*- coding: utf-8 -*-

import flask
import json
import mwapi  # type: ignore
import mwoauth  # type: ignore
import os
import random
import requests
import requests_oauthlib  # type: ignore
import string
import toolforge
from typing import List, Optional, Tuple, Union
import werkzeug
import yaml

from converters import EntityIdConverter, PropertyIdConverter, \
    RankConverter, WikiConverter
import wbformat


app = flask.Flask(__name__)

user_agent = toolforge.set_user_agent(
    'ranker',
    email='ranker@lucaswerkmeister.de')

__dir__ = os.path.dirname(__file__)
try:
    with open(os.path.join(__dir__, 'config.yaml')) as config_file:
        app.config.update(yaml.safe_load(config_file))
except FileNotFoundError:
    print('config.yaml file not found, assuming local development setup')
    characters = string.ascii_letters + string.digits
    random_string = ''.join(random.choice(characters) for _ in range(64))
    app.secret_key = random_string

if 'oauth' in app.config:
    oauth_config = app.config['oauth']
    consumer_token = mwoauth.ConsumerToken(oauth_config['consumer_key'],
                                           oauth_config['consumer_secret'])
    index_php = 'https://www.wikidata.org/w/index.php'


app.url_map.converters['eid'] = EntityIdConverter
app.url_map.converters['pid'] = PropertyIdConverter
app.url_map.converters['rank'] = RankConverter
app.url_map.converters['wiki'] = WikiConverter


@app.template_global()
def csrf_token() -> str:
    if 'csrf_token' not in flask.session:
        characters = string.ascii_letters + string.digits
        random_string = ''.join(random.choice(characters) for _ in range(64))
        flask.session['csrf_token'] = random_string
    return flask.session['csrf_token']


@app.template_global()
def form_value(name: str) -> flask.Markup:
    if 'repeat_form' in flask.g and name in flask.request.form:
        return (flask.Markup(r' value="') +
                flask.Markup.escape(flask.request.form[name]) +
                flask.Markup(r'" '))
    else:
        return flask.Markup()


@app.template_global()
def form_attributes(name: str) -> flask.Markup:
    return (flask.Markup(r' id="') +
            flask.Markup.escape(name) +
            flask.Markup(r'" name="') +
            flask.Markup.escape(name) +
            flask.Markup(r'" ') +
            form_value(name))


@app.template_filter()
def user_link(user_name: str) -> flask.Markup:
    user_href = 'https://www.wikidata.org/wiki/User:'
    return (flask.Markup(r'<a href="' + user_href) +
            flask.Markup.escape(user_name.replace(' ', '_')) +
            flask.Markup(r'">') +
            flask.Markup(r'<bdi>') +
            flask.Markup.escape(user_name) +
            flask.Markup(r'</bdi>') +
            flask.Markup(r'</a>'))


@app.template_global()
def authentication_area() -> flask.Markup:
    if 'oauth' not in app.config:
        return flask.Markup()

    if 'oauth_access_token' not in flask.session:
        return (flask.Markup(r'<a id="login" class="navbar-text" href="') +
                flask.Markup.escape(flask.url_for('login')) +
                flask.Markup(r'">Log in</a>'))

    access_token = mwoauth.AccessToken(**flask.session['oauth_access_token'])
    identity = mwoauth.identify(index_php,
                                consumer_token,
                                access_token)

    return (flask.Markup(r'<span class="navbar-text">Logged in as ') +
            user_link(identity['username']) +
            flask.Markup(r'</span>'))


@app.template_global()
def can_edit() -> bool:
    if 'oauth' not in app.config:
        return True
    return 'oauth_access_token' in flask.session


@app.template_global()
def format_value(wiki: str, property_id: str, value: dict) -> flask.Markup:
    return wbformat.format_value(anonymous_session(wiki), property_id, value)


@app.template_global()
def format_property(wiki: str, property_id: str) -> flask.Markup:
    return wbformat.format_property(anonymous_session(wiki), property_id)


def anonymous_session(wiki: str) -> mwapi.Session:
    return mwapi.Session('https://' + wiki,
                         user_agent=user_agent)


def authenticated_session(wiki: str) -> Optional[mwapi.Session]:
    if 'oauth_access_token' not in flask.session:
        return None

    access_token = mwoauth.AccessToken(
        **flask.session['oauth_access_token'])
    auth = requests_oauthlib.OAuth1(client_key=consumer_token.key,
                                    client_secret=consumer_token.secret,
                                    resource_owner_key=access_token.key,
                                    resource_owner_secret=access_token.secret)
    return mwapi.Session(host='https://' + wiki,
                         auth=auth,
                         user_agent=user_agent)


@app.route('/', methods=['GET', 'POST'])
def index() -> Union[str, werkzeug.Response]:
    if flask.request.method == 'POST':
        url = flask.url_for('show_edit_form',
                            wiki=flask.request.form['wiki'],
                            entity_id=flask.request.form['entity_id'],
                            property_id=flask.request.form['property_id'])
        return flask.redirect(url)
    return flask.render_template('index.html')


@app.route('/edit/<wiki:wiki>/<eid:entity_id>/<pid:property_id>/')
def show_edit_form(wiki: str, entity_id: str, property_id: str) -> str:
    session = anonymous_session(wiki)
    response = session.get(action='wbgetentities',
                           ids=[entity_id],
                           props=['info', 'claims'],
                           formatversion=2)
    entity = response['entities'][entity_id]
    base_revision_id = entity['lastrevid']
    statements = entity_statements(entity, property_id)

    prefetch_property_ids = {property_id}
    for statement in statements:
        prefetch_property_ids.update(statement.get('qualifiers', {}).keys())
    wbformat.prefetch_properties(session, prefetch_property_ids)

    return flask.render_template('edit.html',
                                 wiki=wiki,
                                 entity_id=entity_id,
                                 property_id=property_id,
                                 statements=statements,
                                 base_revision_id=base_revision_id)


@app.route('/edit/<wiki:wiki>/<eid:entity_id>/<pid:property_id>/set/<rank:rank>',  # noqa:E501
           methods=['POST'])
def edit_set_rank(wiki: str, entity_id: str, property_id: str, rank: str) \
        -> Union[werkzeug.Response, Tuple[str, int]]:
    if not submitted_request_valid():
        return 'CSRF error', 400  # TODO better error

    if 'oauth_access_token' not in flask.session:
        return 'not logged in', 401  # TODO better error
    session = authenticated_session(wiki)
    assert session is not None

    base_revision_id = flask.request.form['base_revision_id']
    response = requests.get(f'https://{wiki}/wiki/Special:EntityData/'
                            f'{entity_id}.json?revision={base_revision_id}')
    entity = response.json()['entities'][entity_id]
    statements = entity_statements(entity, property_id)

    edited_statements = 0
    for statement in statements:
        if statement['id'] in flask.request.form:
            statement['rank'] = rank
            edited_statements += 1

    edited_entity = build_entity(entity_id, property_id, statements)
    if edited_statements == 1:
        summary = f'Set rank of 1 statement to "{rank}"'
    else:
        summary = f'Set rank of {edited_statements} statements to "{rank}"'
    if flask.request.form.get('summary'):
        summary += ': ' + flask.request.form['summary']

    return save_entity_and_redirect(edited_entity,
                                    summary,
                                    base_revision_id,
                                    session)


@app.route('/edit/<wiki:wiki>/<eid:entity_id>/<pid:property_id>/increment',
           methods=['POST'])
def edit_increment_rank(wiki: str, entity_id: str, property_id: str) \
        -> Union[werkzeug.Response, Tuple[str, int]]:
    if not submitted_request_valid():
        return 'CSRF error', 400  # TODO better error

    if 'oauth_access_token' not in flask.session:
        return 'not logged in', 401  # TODO better error
    session = authenticated_session(wiki)
    assert session is not None

    base_revision_id = flask.request.form['base_revision_id']
    response = requests.get(f'https://{wiki}/wiki/Special:EntityData/'
                            f'{entity_id}.json?revision={base_revision_id}')
    entity = response.json()['entities'][entity_id]
    statements = entity_statements(entity, property_id)

    edited_statements = 0
    for statement in statements:
        if statement['id'] in flask.request.form:
            rank = statement['rank']
            incremented_rank = increment_rank(rank)
            if incremented_rank != rank:
                statement['rank'] = incremented_rank
                edited_statements += 1

    edited_entity = build_entity(entity_id, property_id, statements)
    if edited_statements == 1:
        summary = 'Incremented rank of 1 statement'
    else:
        summary = f'Incremented rank of {edited_statements} statements'
    if flask.request.form.get('summary'):
        summary += ': ' + flask.request.form['summary']

    return save_entity_and_redirect(edited_entity,
                                    summary,
                                    base_revision_id,
                                    session)


@app.route('/login')
def login() -> werkzeug.Response:
    redirect, request_token = mwoauth.initiate(index_php,
                                               consumer_token,
                                               user_agent=user_agent)
    flask.session['oauth_request_token'] = dict(zip(request_token._fields,
                                                    request_token))
    return flask.redirect(redirect)


@app.route('/oauth/callback')
def oauth_callback() -> werkzeug.Response:
    request_token = mwoauth.RequestToken(
        **flask.session.pop('oauth_request_token'))
    access_token = mwoauth.complete(index_php,
                                    consumer_token,
                                    request_token,
                                    flask.request.query_string,
                                    user_agent=user_agent)
    flask.session['oauth_access_token'] = dict(zip(access_token._fields,
                                                   access_token))
    flask.session.pop('csrf_token', None)
    return flask.redirect(flask.url_for('index'))


@app.route('/logout')
def logout() -> werkzeug.Response:
    flask.session.pop('oauth_access_token', None)
    return flask.redirect(flask.url_for('index'))


def full_url(endpoint: str, **kwargs) -> str:
    scheme = flask.request.headers.get('X-Forwarded-Proto', 'http')
    return flask.url_for(endpoint, _external=True, _scheme=scheme, **kwargs)


def submitted_request_valid() -> bool:
    """Check whether a submitted POST request is valid.

    If this method returns False, the request might have been issued
    by an attacker as part of a Cross-Site Request Forgery attack;
    callers MUST NOT process the request in that case.
    """
    real_token = flask.session.get('csrf_token')
    submitted_token = flask.request.form.get('csrf_token')
    if not real_token:
        # we never expected a POST
        return False
    if not submitted_token:
        # token got lost or attacker did not supply it
        return False
    if submitted_token != real_token:
        # incorrect token (could be outdated or incorrectly forged)
        return False
    return True


@app.after_request
def deny_frame(response: flask.Response) -> flask.Response:
    """Disallow embedding the tool’s pages in other websites.

    Not every tool can be usefully embedded in other websites, but
    allowing embedding can expose the tool to clickjacking
    vulnerabilities, so err on the side of caution and disallow
    embedding. This can be removed (possibly only for certain pages)
    as long as other precautions against clickjacking are taken.
    """
    response.headers['X-Frame-Options'] = 'deny'
    return response


def entity_statements(entity: dict, property_id: str) -> List[dict]:
    if entity.get('type') == 'mediainfo':  # optional due to T272804
        statements = entity['statements']
    else:
        statements = entity['claims']
    return statements.setdefault(property_id, [])


def increment_rank(rank: str) -> str:
    return {
        'deprecated': 'normal',
        'normal': 'preferred',
        'preferred': 'preferred',
    }[rank]


def build_entity(entity_id: str,
                 property_id: str,
                 statements: List[dict]) -> dict:
    return {
        'id': entity_id,
        'claims': {  # yes, 'claims' even for MediaInfo entities
            property_id: statements,
        },
    }


def save_entity_and_redirect(entity_data: dict,
                             summary: str,
                             base_revision_id: int,
                             session: mwapi.Session) -> werkzeug.Response:

    token = session.get(action='query',
                        meta='tokens',
                        type='csrf')['query']['tokens']['csrftoken']

    api_response = session.post(action='wbeditentity',
                                id=entity_data['id'],
                                data=json.dumps(entity_data),
                                summary=summary,
                                baserevid=base_revision_id,
                                token=token)
    revision_id = api_response['entity']['lastrevid']

    return flask.redirect(f'{session.host}/w/index.php'
                          f'?diff={revision_id}&oldid={base_revision_id}')
