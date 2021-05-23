# -*- coding: utf-8 -*-

import flask
import json
import mwapi  # type: ignore
import mwoauth  # type: ignore
import os
import random
import re
import requests
import requests_oauthlib  # type: ignore
import string
import sys
import toolforge
from typing import Dict, Container, Iterable, List, Optional, Tuple, Union
import werkzeug
import yaml

from converters import EntityIdConverter, PropertyIdConverter, \
    RankConverter, WikiConverter, WikiWithQueryServiceConverter, \
    WikiWithoutQueryServiceException
from query_service import query_wiki, query_service_name, query_service_url
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
app.url_map.converters['wwqs'] = WikiWithQueryServiceConverter


@app.template_global()
def csrf_token() -> str:
    """Get a CSRF token for the current session in the tool.

    Not to be confused with edit_token,
    which gets a token for use with the MediaWiki API."""

    if 'csrf_token' not in flask.session:
        characters = string.ascii_letters + string.digits
        random_string = ''.join(random.choice(characters) for _ in range(64))
        flask.session['csrf_token'] = random_string
    return flask.session['csrf_token']


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

    session = authenticated_session('www.wikidata.org')
    if session is None:
        return (flask.Markup(r'<a id="login" class="navbar-text" href="') +
                flask.Markup.escape(flask.url_for('login')) +
                flask.Markup(r'">Log in</a>'))

    userinfo = session.get(action='query',
                           meta='userinfo')['query']['userinfo']

    return (flask.Markup(r'<span class="navbar-text">Logged in as ') +
            user_link(userinfo['name']) +
            flask.Markup(r'</span>'))


@app.template_global()
def can_edit() -> bool:
    if 'oauth' not in app.config:
        return True
    return 'oauth_access_token' in flask.session


@app.template_global()  # type: ignore
def has_query_service(wiki: str) -> bool:
    try:
        app.url_map.converters['wwqs'](app.url_map).to_python(wiki)
        return True
    except WikiWithoutQueryServiceException:
        return False


@app.template_global()  # type: ignore
def format_value(wiki: str, property_id: str, value: dict) -> flask.Markup:
    return wbformat.format_value(anonymous_session(wiki), property_id, value)


@app.template_global()  # type: ignore
def format_entity(wiki: str, entity_id: str) -> flask.Markup:
    return wbformat.format_entity(anonymous_session(wiki), entity_id)


@app.template_filter()
def format_query_service(wiki: str) -> flask.Markup:
    return (flask.Markup(r'<a href="') +
            flask.Markup.escape(query_service_url(wiki)) +
            flask.Markup(r'">') +
            flask.Markup.escape(query_service_name(wiki)) +
            flask.Markup(r'</a>'))


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
        form = flask.request.form
        wiki = form['wiki']
        entity_id = form['entity_id']
        if entity_id.startswith('File:'):
            try:
                session = anonymous_session(wiki)
                response = session.get(action='query',
                                       titles=[entity_id],
                                       formatversion=2)
                page_id = response['query']['pages'][0]['pageid']
                entity_id = f'M{page_id}'
            except Exception:
                pass  # leave entity_id as it is
        url = flask.url_for('show_edit_form',
                            wiki=wiki,
                            entity_id=entity_id,
                            property_id=form['property_id'])
        return flask.redirect(url)
    args = flask.request.args
    return flask.render_template('index.html',
                                 wiki=args.get('wiki'),
                                 entity_id=args.get('entity_id'),
                                 property_id=args.get('property_id'))


@app.route('/edit/<wiki:wiki>/<eid:entity_id>/<pid:property_id>/')
def show_edit_form(wiki: str, entity_id: str, property_id: str) \
        -> Union[str, Tuple[str, int]]:
    session = anonymous_session(wiki)
    entity = get_entities(session, [entity_id])[entity_id]
    if 'missing' in entity:
        return flask.render_template('no-such-entity.html',
                                     wiki=wiki,
                                     entity_id=entity_id), 404
    base_revision_id = entity['lastrevid']
    statements = entity_statements(entity).get(property_id, [])

    prefetch_entity_ids = {entity_id, property_id}
    for statement in statements:
        prefetch_entity_ids.update(statement.get('qualifiers', {}).keys())
    wbformat.prefetch_entities(session, prefetch_entity_ids)

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

    session = authenticated_session(wiki)
    if session is None:
        return 'not logged in', 401  # TODO better error

    statement_ids = flask.request.form
    custom_summary = flask.request.form.get('summary')
    base_revision_id = flask.request.form['base_revision_id']
    response = requests.get(f'https://{wiki}/wiki/Special:EntityData/'
                            f'{entity_id}.json?revision={base_revision_id}')
    entity = response.json()['entities'][entity_id]
    statements = entity_statements(entity).get(property_id, [])

    statement_groups, edited_statements = statements_set_rank_to(
        statement_ids,
        rank,
        {property_id: statements},
        property_id,
    )

    edited_entity = build_entity(entity_id, statement_groups)
    summary = get_summary_set_rank(edited_statements,
                                   rank,
                                   custom_summary)

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

    session = authenticated_session(wiki)
    if session is None:
        return 'not logged in', 401  # TODO better error

    statement_ids = flask.request.form
    custom_summary = flask.request.form.get('summary')
    base_revision_id = flask.request.form['base_revision_id']
    response = requests.get(f'https://{wiki}/wiki/Special:EntityData/'
                            f'{entity_id}.json?revision={base_revision_id}')
    entity = response.json()['entities'][entity_id]
    statements = entity_statements(entity).get(property_id, [])

    statement_groups, edited_statements = statements_increment_rank(
        statement_ids,
        {property_id: statements},
        property_id,
    )

    edited_entity = build_entity(entity_id, {property_id: statements})
    summary = get_summary_increment_rank(edited_statements,
                                         custom_summary)

    return save_entity_and_redirect(edited_entity,
                                    summary,
                                    base_revision_id,
                                    session)


@app.route('/batch/list/collective/<wiki:wiki>/')
def show_batch_list_collective_form(wiki: str) -> str:
    return flask.render_template('batch-list-collective.html',
                                 wiki=wiki)


@app.route('/batch/list/collective/<wiki:wiki>/set/<rank:rank>',
           methods=['POST'])
def batch_list_set_rank(wiki: str, rank: str) \
        -> Union[str, Tuple[str, int]]:
    if not submitted_request_valid():
        return 'CSRF error', 400  # TODO better error

    session = authenticated_session(wiki)
    if session is None:
        return 'not logged in', 401  # TODO better error

    statement_ids_list = flask.request.form.get('statement_ids', '')
    custom_summary = flask.request.form.get('summary')

    statement_ids_by_entity_id = parse_statement_ids_list(statement_ids_list)

    return batch_set_rank_and_show_results(wiki,
                                           statement_ids_by_entity_id,
                                           rank,
                                           session,
                                           custom_summary)


@app.route('/batch/list/collective/<wiki:wiki>/increment',
           methods=['POST'])
def batch_list_increment_rank(wiki: str) \
        -> Union[str, Tuple[str, int]]:
    if not submitted_request_valid():
        return 'CSRF error', 400  # TODO better error

    session = authenticated_session(wiki)
    if session is None:
        return 'not logged in', 401  # TODO better error

    statement_ids_list = flask.request.form.get('statement_ids', '')
    custom_summary = flask.request.form.get('summary')

    statement_ids_by_entity_id = parse_statement_ids_list(statement_ids_list)

    return batch_increment_rank_and_show_results(wiki,
                                                 statement_ids_by_entity_id,
                                                 session,
                                                 custom_summary)


@app.route('/batch/query/collective/<wwqs:wiki>/')
def show_batch_query_collective_form(wiki: str) -> str:
    return flask.render_template('batch-query-collective.html',
                                 wiki=wiki)


@app.route('/batch/query/collective/<wwqs:wiki>/set/<rank:rank>',
           methods=['POST'])
def batch_query_set_rank(wiki: str, rank: str) \
        -> Union[str, Tuple[str, int]]:
    if not submitted_request_valid():
        return 'CSRF error', 400  # TODO better error

    session = authenticated_session(wiki)
    if session is None:
        return 'not logged in', 401  # TODO better error

    query = flask.request.form.get('query', '')
    custom_summary = flask.request.form.get('summary')

    statement_ids_by_entity_id = query_statement_ids(wiki, query)

    return batch_set_rank_and_show_results(wiki,
                                           statement_ids_by_entity_id,
                                           rank,
                                           session,
                                           custom_summary)


@app.route('/batch/query/collective/<wwqs:wiki>/increment',
           methods=['POST'])
def batch_query_increment_rank(wiki: str) \
        -> Union[str, Tuple[str, int]]:
    if not submitted_request_valid():
        return 'CSRF error', 400  # TODO better error

    session = authenticated_session(wiki)
    if session is None:
        return 'not logged in', 401  # TODO better error

    query = flask.request.form.get('query', '')
    custom_summary = flask.request.form.get('summary')

    statement_ids_by_entity_id = query_statement_ids(wiki, query)

    return batch_increment_rank_and_show_results(wiki,
                                                 statement_ids_by_entity_id,
                                                 session,
                                                 custom_summary)


@app.route('/batch/list/individual/<wiki:wiki>/')
def show_batch_list_individual_form(wiki: str) -> str:
    return flask.render_template('batch-list-individual.html',
                                 wiki=wiki)


@app.route('/batch/list/individual/<wiki:wiki>/',
           methods=['POST'])
def batch_list_edit_rank(wiki: str) -> Union[str, Tuple[str, int]]:
    if not submitted_request_valid():
        return 'CSRF error', 400  # TODO better error

    session = authenticated_session(wiki)
    if session is None:
        return 'not logged in', 401  # TODO better error

    commands_list = flask.request.form.get('commands', '')
    custom_summary = flask.request.form.get('summary')

    commands_by_entity_id = parse_statement_ids_with_ranks(commands_list)

    return batch_edit_rank_and_show_results(wiki,
                                            commands_by_entity_id,
                                            session,
                                            custom_summary)


@app.route('/batch/query/individual/<wwqs:wiki>/')
def show_batch_query_individual_form(wiki: str) -> str:
    return flask.render_template('batch-query-individual.html',
                                 wiki=wiki)


@app.route('/batch/query/individual/<wwqs:wiki>/',
           methods=['POST'])
def batch_query_edit_rank(wiki: str) \
        -> Union[str, Tuple[str, int]]:
    if not submitted_request_valid():
        return 'CSRF error', 400  # TODO better error

    session = authenticated_session(wiki)
    if session is None:
        return 'not logged in', 401  # TODO better error

    query = flask.request.form.get('query', '')
    custom_summary = flask.request.form.get('summary')

    commands_by_entity_id = query_statement_ids_with_ranks(wiki, query)

    return batch_edit_rank_and_show_results(wiki,
                                            commands_by_entity_id,
                                            session,
                                            custom_summary)


@app.route('/login')
def login() -> werkzeug.Response:
    redirect, request_token = mwoauth.initiate(index_php,
                                               consumer_token,
                                               user_agent=user_agent)
    flask.session['oauth_request_token'] = dict(zip(request_token._fields,
                                                    request_token))
    return_url = flask.request.referrer
    if return_url and return_url.startswith(full_url('index')):
        flask.session['oauth_redirect_target'] = return_url
    return flask.redirect(redirect)


@app.route('/oauth/callback')
def oauth_callback() -> Union[werkzeug.Response, str]:
    oauth_request_token = flask.session.pop('oauth_request_token', None)
    if oauth_request_token is None:
        already_logged_in = 'oauth_access_token' in flask.session
        query_string = flask.request.query_string\
                                    .decode(flask.request.url_charset)
        return flask.render_template('no-oauth-request-token.html',
                                     already_logged_in=already_logged_in,
                                     query_string=query_string)
    request_token = mwoauth.RequestToken(**oauth_request_token)
    access_token = mwoauth.complete(index_php,
                                    consumer_token,
                                    request_token,
                                    flask.request.query_string,
                                    user_agent=user_agent)
    flask.session['oauth_access_token'] = dict(zip(access_token._fields,
                                                   access_token))
    flask.session.pop('csrf_token', None)
    redirect_target = flask.session.pop('oauth_redirect_target', None)
    return flask.redirect(redirect_target or flask.url_for('index'))


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


def statement_id_from_uri(uri: str, wiki: str) -> str:
    for protocol in ['http', 'https']:
        prefix = f'{protocol}://{wiki}/entity/statement/'
        if uri.startswith(prefix):
            break
    else:
        raise ValueError('URI {uri} does not belong to wiki {wiki}')
    entity_id, _, guid = uri[len(prefix):].partition('-')
    return f'{entity_id}${guid}'


def rank_from_uri(uri: str) -> str:
    return {
        'http://wikiba.se/ontology#DeprecatedRank': 'deprecated',
        'http://wikiba.se/ontology#NormalRank': 'normal',
        'http://wikiba.se/ontology#PreferredRank': 'preferred',
    }[uri]


def entity_id_from_statement_id(statement_id: str) -> str:
    return statement_id.split('$', 1)[0].upper()


def parse_statement_ids_list(input: str) -> Dict[str, List[str]]:
    statement_ids = input.splitlines()
    statement_ids_by_entity_id: Dict[str, List[str]] = {}
    for statement_id in statement_ids:
        entity_id = entity_id_from_statement_id(statement_id)
        statement_ids_by_entity_id.setdefault(entity_id, [])\
                                  .append(statement_id)
    return statement_ids_by_entity_id


def query_statement_ids(wiki: str, query: str) -> Dict[str, List[str]]:
    results = query_wiki(wiki, query, user_agent)
    assert 'statement' in results['head']['vars']  # TODO better error handling
    statement_ids_by_entity_id: Dict[str, List[str]] = {}
    for result in results['results']['bindings']:
        if result['statement']['type'] != 'uri':
            continue
        statement_id = statement_id_from_uri(result['statement']['value'],
                                             wiki)
        entity_id = entity_id_from_statement_id(statement_id)
        statement_ids_by_entity_id.setdefault(entity_id, [])\
                                  .append(statement_id)
    return statement_ids_by_entity_id


def parse_statement_ids_with_ranks(input: str) \
        -> Dict[str, Dict[str, str]]:
    commands = input.splitlines()
    commands_by_entity_id: Dict[str, Dict[str, str]] = {}
    for command in commands:
        statement_id, rank = re.split('[|\t]', command, maxsplit=1)
        entity_id = entity_id_from_statement_id(statement_id)
        commands_by_entity_id.setdefault(entity_id, {})[statement_id] = rank
    return commands_by_entity_id


def query_statement_ids_with_ranks(wiki: str, query: str) \
        -> Dict[str, Dict[str, str]]:
    results = query_wiki(wiki, query, user_agent)
    # TODO better error handling
    assert 'statement' in results['head']['vars']
    assert 'rank' in results['head']['vars']
    commands_by_entity_id: Dict[str, Dict[str, str]] = {}
    for result in results['results']['bindings']:
        if result['statement']['type'] != 'uri':
            continue
        if result['rank']['type'] != 'uri':
            continue
        statement_id = statement_id_from_uri(result['statement']['value'],
                                             wiki)
        entity_id = entity_id_from_statement_id(statement_id)
        rank = rank_from_uri(result['rank']['value'])
        commands_by_entity_id.setdefault(entity_id, {})[statement_id] = rank
    return commands_by_entity_id


def get_entities(session: mwapi.Session, entity_ids: Iterable[str]) -> dict:
    entity_ids = list(set(entity_ids))
    entities = {}
    for chunk in [entity_ids[i:i+50] for i in range(0, len(entity_ids), 50)]:
        response = session.get(action='wbgetentities',
                               ids=chunk,
                               props=['info', 'claims'],
                               formatversion=2)
        entities.update(response['entities'])
    return entities


def entity_statements(entity: dict) -> Dict[str, List[dict]]:
    if entity.get('type') == 'mediainfo':  # optional due to T272804
        statements = entity['statements']
        if statements == []:
            statements = {}  # work around T222159
    else:
        statements = entity['claims']
    return statements


def increment_rank(rank: str) -> str:
    return {
        'deprecated': 'normal',
        'normal': 'preferred',
        'preferred': 'preferred',
    }[rank]


def statements_set_rank_to(statement_ids: Container[str],
                           rank: str,
                           statements: Dict[str, List[dict]],
                           property_id: Optional[str] = None) \
        -> Tuple[Dict[str, List[dict]], int]:
    """Set the rank of certain statements to a constant value.

    statement_ids specifies the statements to edit, and rank the target rank.
    statements is a mapping from property IDs to statement groups.
    If property_id is given, only statements for that property are checked
    (i.e. the other statements are not inspected, as an optimization).

    Returns a dict of edited statement groups
    (though the lists in the statements parameter are also edited in-place),
    and the number of edited statements."""
    if property_id is None:
        statement_groups = statements
    else:
        statement_groups = {property_id: statements.get(property_id, [])}
    edited_statements = 0
    for statement_group in statement_groups.values():
        for statement in statement_group:
            if statement['id'] in statement_ids and statement['rank'] != rank:
                statement['rank'] = rank
                edited_statements += 1
    return statement_groups, edited_statements


def statements_increment_rank(statement_ids: Container[str],
                              statements: Dict[str, List[dict]],
                              property_id: Optional[str] = None) \
        -> Tuple[Dict[str, List[dict]], int]:
    """Increment the rank of certain statements.

    statement_ids specifies the statements to edit.
    statements is a mapping from property IDs to statement groups.
    If property_id is given, only statements for that property are checked
    (i.e. the other statements are not inspected, as an optimization).

    Returns a dict of edited statement groups
    (though the lists in the statements parameter are also edited in-place),
    and the number of edited statements."""
    if property_id is None:
        statement_groups = statements
    else:
        statement_groups = {property_id: statements.get(property_id, [])}
    edited_statements = 0
    for statement_group in statement_groups.values():
        for statement in statement_group:
            if statement['id'] in statement_ids:
                rank = statement['rank']
                incremented_rank = increment_rank(rank)
                if incremented_rank != rank:
                    statement['rank'] = incremented_rank
                    edited_statements += 1
    return statement_groups, edited_statements


def statements_edit_rank(commands: Dict[str, str],
                         statements: Dict[str, List[dict]]) \
        -> Tuple[Dict[str, List[dict]], int]:
    edited_statements = 0
    for statement_group in statements.values():
        for statement in statement_group:
            if statement['id'] in commands:
                edited_rank = commands[statement['id']]
                if edited_rank != statement['rank']:
                    statement['rank'] = edited_rank
                    edited_statements += 1
    return statements, edited_statements


def build_entity(entity_id: str,
                 statement_groups: Dict[str, List[dict]]) -> dict:
    return {
        'id': entity_id,
        'claims': statement_groups,
        # yes, 'claims' even for MediaInfo entities
    }


def str_strip_optional(s: Optional[str]) -> Optional[str]:
    return s.strip() if s is not None else None


def get_summary_set_rank(edited_statements: int,
                         rank: str,
                         custom_summary: Optional[str]) -> str:
    if edited_statements == 1:
        summary = f'Set rank of 1 statement to {rank}'
    else:
        summary = f'Set rank of {edited_statements} statements to {rank}'
    custom_summary = str_strip_optional(custom_summary)
    if custom_summary:
        summary += ': ' + custom_summary
    return summary


def get_summary_increment_rank(edited_statements: int,
                               custom_summary: Optional[str]) -> str:
    if edited_statements == 1:
        summary = 'Incremented rank of 1 statement'
    else:
        summary = f'Incremented rank of {edited_statements} statements'
    custom_summary = str_strip_optional(custom_summary)
    if custom_summary:
        summary += ': ' + custom_summary
    return summary


def get_summary_edit_rank(edited_statements: int,
                          custom_summary: Optional[str]) -> str:
    if edited_statements == 1:
        summary = 'Edited rank of 1 statement'
    else:
        summary = f'Edited rank of {edited_statements} statements'
    custom_summary = str_strip_optional(custom_summary)
    if custom_summary:
        summary += ': ' + custom_summary
    return summary


def edit_token(session: mwapi.Session) -> str:
    """Get an edit token / CSRF token for the MediaWiki API.

    Not to be confused with csrf_token,
    which gets a token for use within the tool."""

    edit_tokens = flask.g.setdefault('edit_tokens', {})  # type: ignore
    key = session.host
    if key in edit_tokens:
        return edit_tokens[key]

    token = session.get(action='query',
                        meta='tokens',
                        type='csrf')['query']['tokens']['csrftoken']
    edit_tokens[key] = token
    return token


def save_entity(entity_data: dict,
                summary: str,
                base_revision_id: Union[int, str],
                session: mwapi.Session) -> int:

    token = edit_token(session)

    api_response = session.post(action='wbeditentity',
                                id=entity_data['id'],
                                data=json.dumps(entity_data),
                                summary=summary,
                                baserevid=base_revision_id,
                                token=token)
    revision_id = api_response['entity']['lastrevid']

    return revision_id


def save_entity_and_redirect(entity_data: dict,
                             summary: str,
                             base_revision_id: Union[int, str],
                             session: mwapi.Session) -> werkzeug.Response:

    revision_id = save_entity(entity_data,
                              summary,
                              base_revision_id,
                              session)

    return flask.redirect(f'{session.host}/w/index.php'
                          f'?diff={revision_id}&oldid={base_revision_id}')


def batch_set_rank_and_show_results(
        wiki: str,
        statement_ids_by_entity_id: Dict[str, List[str]],
        rank: str,
        session: mwapi.Session,
        custom_summary: Optional[str],
) -> str:
    entities = get_entities(session, statement_ids_by_entity_id.keys())
    edits = {}
    errors = {}

    for entity_id, statement_ids in statement_ids_by_entity_id.items():
        entity = entities[entity_id]
        statements = entity_statements(entity)
        statements, edited_statements = statements_set_rank_to(statement_ids,
                                                               rank,
                                                               statements)
        edited_entity = build_entity(entity_id, statements)
        summary = get_summary_set_rank(edited_statements,
                                       rank,
                                       custom_summary)
        try:
            edits[entity_id] = save_entity(edited_entity,
                                           summary,
                                           entity['lastrevid'],
                                           session)
        except mwapi.errors.APIError as e:
            print('caught error in batch mode:', e, file=sys.stderr)
            errors[entity_id] = e

    wbformat.prefetch_entities(session, statement_ids_by_entity_id.keys())

    return flask.render_template('batch-results.html',
                                 wiki=wiki,
                                 edits=edits,
                                 errors=errors)


def batch_increment_rank_and_show_results(
        wiki: str,
        statement_ids_by_entity_id: Dict[str, List[str]],
        session: mwapi.Session,
        custom_summary: Optional[str],
) -> str:
    entities = get_entities(session, statement_ids_by_entity_id.keys())
    edits = {}
    errors = {}

    for entity_id, statement_ids in statement_ids_by_entity_id.items():
        entity = entities[entity_id]
        statements = entity_statements(entity)
        statements, edited_statements = statements_increment_rank(
            statement_ids,
            statements,
        )
        edited_entity = build_entity(entity_id, statements)
        summary = get_summary_increment_rank(edited_statements,
                                             custom_summary)
        try:
            edits[entity_id] = save_entity(edited_entity,
                                           summary,
                                           entity['lastrevid'],
                                           session)
        except mwapi.errors.APIError as e:
            print('caught error in batch mode:', e, file=sys.stderr)
            errors[entity_id] = e

    wbformat.prefetch_entities(session, statement_ids_by_entity_id.keys())

    return flask.render_template('batch-results.html',
                                 wiki=wiki,
                                 edits=edits,
                                 errors=errors)


def batch_edit_rank_and_show_results(
        wiki: str,
        commands_by_entity_id: Dict[str, Dict[str, str]],
        session: mwapi.Session,
        custom_summary: Optional[str],
) -> str:
    entities = get_entities(session, commands_by_entity_id.keys())
    edits = {}
    errors = {}

    for entity_id, commands in commands_by_entity_id.items():
        entity = entities[entity_id]
        statements = entity_statements(entity)
        statements, edited_statements = statements_edit_rank(commands,
                                                             statements)
        edited_entity = build_entity(entity_id, statements)
        summary = get_summary_edit_rank(edited_statements,
                                        custom_summary)
        try:
            edits[entity_id] = save_entity(edited_entity,
                                           summary,
                                           entity['lastrevid'],
                                           session)
        except mwapi.errors.APIError as e:
            print('caught error in batch mode:', e, file=sys.stderr)
            errors[entity_id] = e

    wbformat.prefetch_entities(session, commands_by_entity_id.keys())

    return flask.render_template('batch-results.html',
                                 wiki=wiki,
                                 edits=edits,
                                 errors=errors)
