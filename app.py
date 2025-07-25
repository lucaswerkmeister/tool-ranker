# -*- coding: utf-8 -*-

import flask
from flask.typing import ResponseReturnValue as RRV
import json
from markupsafe import Markup
import mwapi  # type: ignore
import mwoauth  # type: ignore
import random
import re
import requests
import requests_oauthlib  # type: ignore
import string
import sys
import toolforge
from toolforge_i18n import ToolforgeI18n, \
    interface_language_code_from_request, lang_autonym, message
from typing import Container, Dict, \
    Iterable, List, Optional, Tuple
import werkzeug
import yaml

from converters import EntityIdConverter, PropertyIdConverter, \
    RankConverter, WikiConverter, WikiWithQueryServiceConverter, \
    WikiWithoutQueryServiceException
from query_service import query_wiki, \
    query_service_id, query_service_url
import wbformat


def interface_language_code(translations):
    if 'uselang' in flask.request.args:
        return interface_language_code_from_request(translations)
    elif flask.session.get('interface_language_code') in translations:
        return flask.session['interface_language_code']
    else:
        return interface_language_code_from_request(translations)


app = flask.Flask(__name__)
i18n = ToolforgeI18n(app, interface_language_code)

user_agent = toolforge.set_user_agent(
    'ranker',
    email='ranker@lucaswerkmeister.de')


app.config.from_file('config.yaml',
                     load=toolforge.load_private_yaml,
                     silent=True)
app.config.from_prefixed_env('TOOL',
                             loads=yaml.safe_load)
if 'OAUTH' in app.config:
    oauth_config = app.config['OAUTH']
    consumer_token = mwoauth.ConsumerToken(oauth_config['CONSUMER_KEY'],
                                           oauth_config['CONSUMER_SECRET'])
    index_php = 'https://www.wikidata.org/w/index.php'
    assert app.secret_key is not None, \
        'If OAuth is configured, the SECRET_KEY must also be configured ' \
        '(a fixed random string)'
else:
    print('No OAuth configuration found, assuming local development setup')
    if app.secret_key is None:
        characters = string.ascii_letters + string.digits
        random_string = ''.join(random.choice(characters) for _ in range(64))
        app.secret_key = random_string


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
def user_link(user_name: str) -> Markup:
    user_href = 'https://www.wikidata.org/wiki/User:'
    return (Markup(r'<a href="' + user_href) +
            Markup.escape(user_name.replace(' ', '_')) +
            Markup(r'">') +
            Markup(r'<bdi>') +
            Markup.escape(user_name) +
            Markup(r'</bdi>') +
            Markup(r'</a>'))


@app.template_global()
def authentication_area() -> Markup:
    if 'OAUTH' not in app.config:
        return Markup()

    session = authenticated_session('www.wikidata.org')
    if session is None:
        return (Markup(r'<a id="login" class="nav-link" href="') +
                Markup.escape(flask.url_for('login')) +
                Markup(r'">') +
                message('nav-login') +
                Markup(r'</a>'))

    userinfo = session.get(action='query',
                           meta='userinfo')['query']['userinfo']

    user_name = userinfo['name']
    logged_in_message = message('nav-logged-in',
                                user_name=user_name,
                                user_link=user_link(user_name))
    return (Markup(r'<span class="nav-link">') +
            logged_in_message +
            Markup(r'</span>'))


@app.template_global()
def can_edit() -> bool:
    if 'OAUTH' not in app.config:
        return True
    return 'oauth_access_token' in flask.session


@app.template_global()
def has_query_service(wiki: str) -> bool:
    try:
        app.url_map.converters['wwqs'](app.url_map).to_python(wiki)
        return True
    except WikiWithoutQueryServiceException:
        return False


@app.template_global()
def format_value(wiki: str, property_id: str, value: dict) -> Markup:
    return wbformat.format_value(anonymous_session(wiki),
                                 flask.g.interface_language_code,
                                 property_id,
                                 value)


@app.template_global()
def format_entity(wiki: str, entity_id: str) -> Markup:
    return wbformat.format_entity(anonymous_session(wiki),
                                  flask.g.interface_language_code,
                                  entity_id)


@app.template_global()
def batch_query_collective_message(wiki: str) -> Markup:
    message_key = f'batch-query-collective-input-{query_service_id(wiki)}'
    return message(message_key, url=query_service_url(wiki))


@app.template_global()
def batch_query_individual_message(wiki: str) -> Markup:
    message_key = f'batch-query-individual-input-{query_service_id(wiki)}'
    return message(message_key, url=query_service_url(wiki))


@app.template_filter()
def wiki_reason_wiki(wiki: str) -> str:
    """The wiki which contains the deprecation reasons for the given wiki."""
    return {
        'www.wikidata.org': 'www.wikidata.org',
        'commons.wikimedia.org': 'www.wikidata.org',
        'test.wikidata.org': 'test.wikidata.org',
        'test-commons.wikimedia.org': 'test.wikidata.org',
    }[wiki]


@app.template_filter()
def wiki_reasons_preferred(wiki: str) -> list[str]:
    if wiki_reason_wiki(wiki) == 'www.wikidata.org':
        return [
            'Q71533355',  # most recent value
            'Q71536040',  # most precise value
            'Q98386534',  # best referenced value
            'Q71536244',  # currently valid value
        ]
    return []


@app.template_filter()
def wiki_reasons_deprecated(wiki: str) -> list[str]:
    if wiki_reason_wiki(wiki) == 'www.wikidata.org':
        return [
            'Q25895909',  # cannot be confirmed by other sources
            'Q21655367',  # not been able to confirm this claim
            'Q14946528',  # conflation
            'Q41755623',  # incorrect value
            'Q21441764',  # withdrawn identifier value
            'Q54975531',  # incorrect identifier value
            'Q54976355',  # unrecognized identifier value
            'Q1193907',  # link rot
        ]
    return []


@app.template_filter()
def wiki_reason_preferred_property(wiki: str) -> Optional[str]:
    if wiki_reason_wiki(wiki) == 'www.wikidata.org':
        return 'P7452'
    return None


@app.template_filter()
def wiki_reason_deprecated_property(wiki: str) -> Optional[str]:
    if wiki_reason_wiki(wiki) == 'www.wikidata.org':
        return 'P2241'
    return None


@app.template_global()
def prefetch_entities(wiki: str, entity_ids: list[str]) -> None:
    wbformat.prefetch_entities(anonymous_session(wiki),
                               flask.g.interface_language_code,
                               entity_ids)


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


@app.route('/')
def index() -> RRV:
    args = flask.request.args
    return flask.render_template('index.html',
                                 wiki=args.get('wiki'),
                                 entity_id=args.get('entity_id'),
                                 property_id=args.get('property_id'))


@app.route('/', methods=['POST'])
def redirect_edit() -> RRV:
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


@app.route('/batch/list/collective/', methods=['POST'])
def redirect_batch_list_collective() -> RRV:
    return flask.redirect(flask.url_for('show_batch_list_collective_form',
                                        wiki=flask.request.form['wiki']))


@app.route('/batch/list/individual/', methods=['POST'])
def redirect_batch_list_individual() -> RRV:
    return flask.redirect(flask.url_for('show_batch_list_individual_form',
                                        wiki=flask.request.form['wiki']))


@app.route('/batch/query/collective/', methods=['POST'])
def redirect_batch_query_collective() -> RRV:
    return flask.redirect(flask.url_for('show_batch_query_collective_form',
                                        wiki=flask.request.form['wiki']))


@app.route('/batch/query/individual/', methods=['POST'])
def redirect_batch_query_individual() -> RRV:
    return flask.redirect(flask.url_for('show_batch_query_individual_form',
                                        wiki=flask.request.form['wiki']))


@app.route('/edit/<wiki:wiki>/<eid:entity_id>/<pid:property_id>/')
def show_edit_form(wiki: str, entity_id: str, property_id: str) -> RRV:
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
    wbformat.prefetch_entities(session,
                               flask.g.interface_language_code,
                               prefetch_entity_ids)

    return flask.render_template('edit.html',
                                 wiki=wiki,
                                 entity_id=entity_id,
                                 property_id=property_id,
                                 statements=statements,
                                 base_revision_id=base_revision_id)


@app.route('/edit/<wiki:wiki>/<eid:entity_id>/<pid:property_id>/set/<rank:rank>',  # noqa:E501
           methods=['POST'])
def edit_set_rank(wiki: str, entity_id: str, property_id: str, rank: str) \
        -> RRV:
    if not submitted_request_valid():
        return 'CSRF error', 400  # TODO better error

    session = authenticated_session(wiki)
    if session is None:
        return 'not logged in', 401  # TODO better error

    statement_ids = flask.request.form
    reason = flask.request.form.get('reason')
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
        wiki,
        reason,
    )

    if not edited_statements:
        return redirect(session, base_revision_id)

    edited_entity = build_entity(entity_id, statement_groups)
    summary = get_summary_set_rank(edited_statements,
                                   rank,
                                   wiki,
                                   reason,
                                   custom_summary)

    return save_entity_and_redirect(edited_entity,
                                    summary,
                                    base_revision_id,
                                    session)


@app.route('/edit/<wiki:wiki>/<eid:entity_id>/<pid:property_id>/increment',
           methods=['POST'])
def edit_increment_rank(wiki: str, entity_id: str, property_id: str) -> RRV:
    if not submitted_request_valid():
        return 'CSRF error', 400  # TODO better error

    session = authenticated_session(wiki)
    if session is None:
        return 'not logged in', 401  # TODO better error

    statement_ids = flask.request.form
    reason = flask.request.form.get('reason')
    custom_summary = flask.request.form.get('summary')
    base_revision_id = flask.request.form['base_revision_id']
    response = requests.get(f'https://{wiki}/wiki/Special:EntityData/'
                            f'{entity_id}.json?revision={base_revision_id}')
    entity = response.json()['entities'][entity_id]
    statements = entity_statements(entity).get(property_id, [])

    statement_groups, edited_statements = statements_increment_rank(
        statement_ids,
        {property_id: statements},
        wiki,
        reason,
    )

    if not edited_statements:
        return redirect(session, base_revision_id)

    edited_entity = build_entity(entity_id, {property_id: statements})
    summary = get_summary_increment_rank(edited_statements,
                                         custom_summary)

    return save_entity_and_redirect(edited_entity,
                                    summary,
                                    base_revision_id,
                                    session)


@app.route('/batch/list/collective/<wiki:wiki>/')
def show_batch_list_collective_form(wiki: str) -> RRV:
    return flask.render_template('batch-list-collective.html',
                                 wiki=wiki)


@app.route('/batch/list/collective/<wiki:wiki>/set/<rank:rank>',
           methods=['POST'])
def batch_list_set_rank(wiki: str, rank: str) -> RRV:
    if not submitted_request_valid():
        return 'CSRF error', 400  # TODO better error

    session = authenticated_session(wiki)
    if session is None:
        return 'not logged in', 401  # TODO better error

    statement_ids_list = flask.request.form.get('statement_ids', '')
    reason = flask.request.form.get('reason')
    custom_summary = flask.request.form.get('summary')

    statement_ids_by_entity_id = parse_statement_ids_list(statement_ids_list)

    return batch_set_rank_and_show_results(wiki,
                                           statement_ids_by_entity_id,
                                           rank,
                                           reason,
                                           session,
                                           custom_summary)


@app.route('/batch/list/collective/<wiki:wiki>/increment',
           methods=['POST'])
def batch_list_increment_rank(wiki: str) -> RRV:
    if not submitted_request_valid():
        return 'CSRF error', 400  # TODO better error

    session = authenticated_session(wiki)
    if session is None:
        return 'not logged in', 401  # TODO better error

    statement_ids_list = flask.request.form.get('statement_ids', '')
    reason = flask.request.form.get('reason')
    custom_summary = flask.request.form.get('summary')

    statement_ids_by_entity_id = parse_statement_ids_list(statement_ids_list)

    return batch_increment_rank_and_show_results(wiki,
                                                 statement_ids_by_entity_id,
                                                 reason,
                                                 session,
                                                 custom_summary)


@app.route('/batch/query/collective/<wwqs:wiki>/')
def show_batch_query_collective_form(wiki: str) -> RRV:
    return flask.render_template('batch-query-collective.html',
                                 wiki=wiki)


@app.route('/batch/query/collective/<wwqs:wiki>/set/<rank:rank>',
           methods=['POST'])
def batch_query_set_rank(wiki: str, rank: str) -> RRV:
    if not submitted_request_valid():
        return 'CSRF error', 400  # TODO better error

    session = authenticated_session(wiki)
    if session is None:
        return 'not logged in', 401  # TODO better error

    query = flask.request.form.get('query', '')
    reason = flask.request.form.get('reason')
    custom_summary = flask.request.form.get('summary')

    statement_ids_by_entity_id = query_statement_ids(wiki, query)

    return batch_set_rank_and_show_results(wiki,
                                           statement_ids_by_entity_id,
                                           rank,
                                           reason,
                                           session,
                                           custom_summary)


@app.route('/batch/query/collective/<wwqs:wiki>/increment',
           methods=['POST'])
def batch_query_increment_rank(wiki: str) -> RRV:
    if not submitted_request_valid():
        return 'CSRF error', 400  # TODO better error

    session = authenticated_session(wiki)
    if session is None:
        return 'not logged in', 401  # TODO better error

    query = flask.request.form.get('query', '')
    reason = flask.request.form.get('reason')
    custom_summary = flask.request.form.get('summary')

    statement_ids_by_entity_id = query_statement_ids(wiki, query)

    return batch_increment_rank_and_show_results(wiki,
                                                 statement_ids_by_entity_id,
                                                 reason,
                                                 session,
                                                 custom_summary)


@app.route('/batch/list/individual/<wiki:wiki>/')
def show_batch_list_individual_form(wiki: str) -> RRV:
    return flask.render_template('batch-list-individual.html',
                                 wiki=wiki)


@app.route('/batch/list/individual/<wiki:wiki>/',
           methods=['POST'])
def batch_list_edit_rank(wiki: str) -> RRV:
    if not submitted_request_valid():
        return 'CSRF error', 400  # TODO better error

    session = authenticated_session(wiki)
    if session is None:
        return 'not logged in', 401  # TODO better error

    commands_list = flask.request.form.get('commands', '')
    custom_summary = flask.request.form.get('summary')

    commands_by_entity_id = parse_statement_ids_with_ranks_and_reasons(
        commands_list,
    )

    return batch_edit_rank_and_show_results(wiki,
                                            commands_by_entity_id,
                                            session,
                                            custom_summary)


@app.route('/batch/query/individual/<wwqs:wiki>/')
def show_batch_query_individual_form(wiki: str) -> RRV:
    return flask.render_template('batch-query-individual.html',
                                 wiki=wiki)


@app.route('/batch/query/individual/<wwqs:wiki>/',
           methods=['POST'])
def batch_query_edit_rank(wiki: str) -> RRV:
    if not submitted_request_valid():
        return 'CSRF error', 400  # TODO better error

    session = authenticated_session(wiki)
    if session is None:
        return 'not logged in', 401  # TODO better error

    query = flask.request.form.get('query', '')
    custom_summary = flask.request.form.get('summary')

    commands_by_entity_id = query_statement_ids_with_ranks_and_reasons(
        wiki,
        query,
    )

    return batch_edit_rank_and_show_results(wiki,
                                            commands_by_entity_id,
                                            session,
                                            custom_summary)


@app.get('/settings/')
def settings():
    flask.session['return_to_redirect'] = flask.request.referrer
    return flask.render_template(
        'settings.html',
        languages={
            language_code: lang_autonym(language_code)
            for language_code in i18n.translations
        },
    )


@app.post('/settings/')
def settings_save():
    if 'interface-language-code' in flask.request.form:
        flask.session['interface_language_code'] = \
            flask.request.form['interface-language-code'][:20]
    return flask.redirect(
        flask.session.pop('return_to_redirect', flask.url_for('index')),
    )


@app.route('/login')
def login() -> RRV:
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
def oauth_callback() -> RRV:
    oauth_request_token = flask.session.pop('oauth_request_token', None)
    if oauth_request_token is None:
        already_logged_in = 'oauth_access_token' in flask.session
        query_string = flask.request.query_string\
                                    .decode('utf8')
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
    flask.session.permanent = True
    flask.session.pop('csrf_token', None)
    redirect_target = flask.session.pop('oauth_redirect_target', None)
    return flask.redirect(redirect_target or flask.url_for('index'))


@app.route('/logout')
def logout() -> RRV:
    flask.session.pop('oauth_access_token', None)
    flask.session.permanent = False
    return flask.redirect(flask.url_for('index'))


@app.route('/healthz')
def health() -> RRV:
    return ''


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


def item_id_from_uri(uri: str, wiki: str) -> str:
    if wiki in {'www.wikidata.org', 'commons.wikimedia.org'}:
        item_wiki = 'www.wikidata.org'
    else:
        item_wiki = 'test.wikidata.org'
    prefix = f'http://{item_wiki}/entity/'
    if uri.startswith(prefix):
        return uri[len(prefix):]
    else:
        raise ValueError(f'URI {uri} does not belong to item wiki {item_wiki}')


def statement_id_from_uri(uri: str, wiki: str) -> str:
    for protocol in ['http', 'https']:
        prefix = f'{protocol}://{wiki}/entity/statement/'
        if uri.startswith(prefix):
            break
    else:
        raise ValueError(f'URI {uri} does not belong to wiki {wiki}')
    dashed_statement_id = uri[len(prefix):]
    entity_id, guid = dashed_statement_id[:-37], dashed_statement_id[-36:]
    return f'{entity_id}${guid}'


def rank_from_uri(uri: str) -> str:
    return {
        'http://wikiba.se/ontology#DeprecatedRank': 'deprecated',
        'http://wikiba.se/ontology#NormalRank': 'normal',
        'http://wikiba.se/ontology#PreferredRank': 'preferred',
    }[uri]


def entity_id_from_statement_id(statement_id: str) -> str:
    try:
        dollar_index = statement_id.index('$')
    except ValueError:
        flask.abort(400, f'{statement_id} does not look like a statement ID'
                    ' (does not contain a dollar sign)')
    else:
        return statement_id[:dollar_index].upper()


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


def parse_statement_ids_with_ranks_and_reasons(input: str) \
        -> Dict[str, Dict[str, Tuple[str, str]]]:
    commands = input.splitlines()
    commands_by_entity_id: Dict[str, Dict[str, Tuple[str, str]]] = {}
    for command in commands:
        statement_id, rank, reason, _ = re.split(
            r'[|\t]',
            command + '||',  # ensure we can unpack reason even if not given
            maxsplit=3,
        )
        entity_id = entity_id_from_statement_id(statement_id)
        commands_by_entity_id.setdefault(entity_id, {})\
            [statement_id] = rank, reason  # noqa: E211
    return commands_by_entity_id


def query_statement_ids_with_ranks_and_reasons(wiki: str, query: str) \
        -> Dict[str, Dict[str, Tuple[str, str]]]:
    results = query_wiki(wiki, query, user_agent)
    # TODO better error handling
    assert 'statement' in results['head']['vars']
    assert 'rank' in results['head']['vars']
    commands_by_entity_id: Dict[str, Dict[str, Tuple[str, str]]] = {}
    for result in results['results']['bindings']:
        if result['statement']['type'] != 'uri':
            continue
        if result['rank']['type'] != 'uri':
            continue
        statement_id = statement_id_from_uri(result['statement']['value'],
                                             wiki)
        entity_id = entity_id_from_statement_id(statement_id)
        rank = rank_from_uri(result['rank']['value'])
        reason_uri = None
        if rank == 'preferred':
            reason_uri = result.get('reasonForPreferredRank', {}).get('value')
        elif rank == 'deprecated':
            reason_uri = result.get('reasonForDeprecatedRank', {}).get('value')
        if not reason_uri:
            reason_uri = result.get('reason', {}).get('value')
        if reason_uri:
            reason = item_id_from_uri(reason_uri, wiki)
        else:
            reason = ''
        commands_by_entity_id.setdefault(entity_id, {})\
            [statement_id] = rank, reason  # noqa: E211
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
                           wiki: str,
                           reason: Optional[str]) \
        -> Tuple[Dict[str, List[dict]], int]:
    """Set the rank of certain statements to a constant value.

    statement_ids is a container (e.g. a set) of statement IDs,
    controlling which of the given statements are actually edited.
    rank is the target rank,
    and statements is a mapping from property IDs to statement groups.
    wiki specifies the wiki the statements belong to,
    and reason is an optional reason for preferred or deprecated rank
    (an exception is raised if a reason is given for normal rank).

    Returns a dict of statement groups of edited statements
    (though the lists in the statements parameter are also edited in-place),
    and the number of edited statements."""
    edited_statement_groups: Dict[str, List[dict]] = {}
    edited_statements = 0
    for property_id, statement_group in statements.items():
        for statement in statement_group:
            if statement['id'] in statement_ids and statement['rank'] != rank:
                statement['rank'] = rank
                statement_remove_reasons(statement, wiki)
                statement_set_reason(statement, rank, wiki, reason)
                edited_statement_groups.setdefault(property_id, [])\
                                       .append(statement)
                edited_statements += 1
    return edited_statement_groups, edited_statements


def statements_increment_rank(statement_ids: Container[str],
                              statements: Dict[str, List[dict]],
                              wiki: str,
                              reason: Optional[str]) \
        -> Tuple[Dict[str, List[dict]], int]:
    """Increment the rank of certain statements.

    statement_ids is a container (e.g. a set) of statement IDs,
    controlling which of the given statements are actually edited.
    statements is a mapping from property IDs to statement groups.
    wiki specifies the wiki the statements belong to.
    reason is mainly included for consistency with statements_set_rank_to,
    an exception is raised whenever it is specified.

    Returns a dict of statement groups of edited statements
    (though the lists in the statements parameter are also edited in-place),
    and the number of edited statements."""
    edited_statement_groups: Dict[str, List[dict]] = {}
    edited_statements = 0
    for property_id, statement_group in statements.items():
        for statement in statement_group:
            if statement['id'] in statement_ids:
                rank = statement['rank']
                incremented_rank = increment_rank(rank)
                if incremented_rank != rank:
                    statement['rank'] = incremented_rank
                    statement_remove_reasons(statement, wiki)
                    if reason:
                        description = ('Specifying a reason when incrementing '
                                       'rank is not supported')
                        flask.abort(400, description=description)
                    edited_statement_groups.setdefault(property_id, [])\
                                           .append(statement)
                    edited_statements += 1
    return edited_statement_groups, edited_statements


def statements_edit_rank(commands: Dict[str, Tuple[str, str]],
                         statements: Dict[str, List[dict]],
                         wiki: str) \
        -> Tuple[Dict[str, List[dict]], int]:
    """Edit the rank of certain statements.

    commands maps statement IDs to a tuple of
    the rank they should have and the reason for it (optional, may be empty).
    statements is a mapping from property IDs to statement groups.
    wiki specifies the wiki the statements belong to.

    Returns the edited statements in the same format
    (in fact, it returns unedited statements too,
    though I don’t remember if this is intentional or not),
    and the number of edited statements."""
    edited_statements = 0
    for statement_group in statements.values():
        for statement in statement_group:
            if statement['id'] in commands:
                rank, reason = commands[statement['id']]
                if rank != statement['rank']:
                    statement['rank'] = rank
                    statement_remove_reasons(statement, wiki)
                    statement_set_reason(statement, rank, wiki, reason)
                    edited_statements += 1
    return statements, edited_statements


def statement_remove_reasons(statement: dict, wiki: str):
    """Remove any reason for preferred / deprecated rank
    qualifiers from the statement."""
    if qualifiers := statement.get('qualifiers', {}):
        qualifiers.pop(wiki_reason_preferred_property(wiki), None)
        qualifiers.pop(wiki_reason_deprecated_property(wiki), None)


def statement_set_reason(
        statement: dict,
        rank: str,
        wiki: str,
        reason: Optional[str],
):
    """Set a reason for preferred / deprecated rank on the statement.

    statement is the statement to be edited and is updated in place.
    rank is rank that the statement is being set to, determining the property.
    wiki specifies the wiki the statement belongs to.
    reason is an item ID; if None or empty, nothing is done."""
    if not reason:
        return
    if rank == 'preferred':
        property_id = wiki_reason_preferred_property(wiki)
    elif rank == 'deprecated':
        property_id = wiki_reason_deprecated_property(wiki)
    else:
        property_id = None
    if property_id is None:
        description = Markup('Cannot set a reason for {} rank on {}')\
            .format(rank, wiki)
        flask.abort(400, description=description)
    qualifiers = statement.setdefault('qualifiers', {})
    assert property_id not in qualifiers, \
        'existing reasons should have been removed already'
    qualifiers[property_id] = [{
        'snaktype': 'value',
        'property': property_id,
        'datatype': 'wikibase-item',
        'datavalue': {
            'type': 'wikibase-entityid',
            'value': {
                'entity-type': 'item',
                'id': reason,
            },
        },
    }]


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
                         wiki: str,
                         reason: Optional[str],
                         custom_summary: Optional[str]) -> str:
    if edited_statements == 1:
        summary = f'Set rank of 1 statement to {rank}'
    else:
        summary = f'Set rank of {edited_statements} statements to {rank}'
    if reason:
        prefix = wiki_reason_summary_prefix(wiki)
        summary += ' (reason: [[' + prefix + reason + ']])'
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


def wiki_reason_summary_prefix(wiki: str) -> str:
    if wiki == 'commons.wikimedia.org':
        return 'd:Special:EntityPage/'
    elif wiki == 'test-commons.wikimedia.org':
        return 'testwikidata:Special:EntityPage/'
    else:
        return ''


def edit_token(session: mwapi.Session) -> str:
    """Get an edit token / CSRF token for the MediaWiki API.

    Not to be confused with csrf_token,
    which gets a token for use within the tool."""

    edit_tokens = flask.g.setdefault('edit_tokens', {})
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
                base_revision_id: int | str,
                session: mwapi.Session) -> int:

    token = edit_token(session)

    api_response = session.post(action='wbeditentity',
                                id=entity_data['id'],
                                data=json.dumps(entity_data),
                                summary=summary,
                                baserevid=base_revision_id,
                                token=token,
                                formatversion=2)
    if api_response['entity'].get('nochange', False):
        print('WARNING: The API returned that no change was made,',
              'so save_entity() should not have been called;',
              f'we edited {entity_data["id"]} as of {base_revision_id},',
              'with the following data:',
              entity_data,
              file=sys.stderr)

    revision_id = api_response['entity']['lastrevid']
    return revision_id


def save_entity_and_redirect(entity_data: dict,
                             summary: str,
                             base_revision_id: int | str,
                             session: mwapi.Session) -> werkzeug.Response:

    revision_id = save_entity(entity_data,
                              summary,
                              base_revision_id,
                              session)

    return redirect(session, base_revision_id, revision_id)


def redirect(session: mwapi.Session,
             base_revision_id: int | str,
             revision_id: Optional[int] = None) -> werkzeug.Response:
    """Redirect to the given edit.

    revision_id may be None to indicate that no edit was made;
    in that case, redirect to the base revision as a permanent link."""

    if revision_id is None:
        query = f'oldid={base_revision_id}'
    else:
        query = f'diff={revision_id}&oldid={base_revision_id}'
    return flask.redirect(f'{session.host}/w/index.php?{query}')


def batch_set_rank_and_show_results(
        wiki: str,
        statement_ids_by_entity_id: Dict[str, List[str]],
        rank: str,
        reason: Optional[str],
        session: mwapi.Session,
        custom_summary: Optional[str],
) -> str:
    entities = get_entities(session, statement_ids_by_entity_id.keys())
    edits = {}
    noops = {}
    errors = {}

    for entity_id, statement_ids in statement_ids_by_entity_id.items():
        entity = entities[entity_id]
        base_revision_id = entity['lastrevid']
        statements = entity_statements(entity)
        statements, edited_statements = statements_set_rank_to(
            statement_ids,
            rank,
            statements,
            wiki,
            reason,
        )
        if not edited_statements:
            noops[entity_id] = base_revision_id
            continue
        edited_entity = build_entity(entity_id, statements)
        summary = get_summary_set_rank(edited_statements,
                                       rank,
                                       wiki,
                                       reason,
                                       custom_summary)
        try:
            edits[entity_id] = save_entity(edited_entity,
                                           summary,
                                           base_revision_id,
                                           session)
        except mwapi.errors.APIError as e:
            print('caught error in batch mode:', e, file=sys.stderr)
            errors[entity_id] = e

    wbformat.prefetch_entities(session,
                               flask.g.interface_language_code,
                               statement_ids_by_entity_id.keys())

    return flask.render_template('batch-results.html',
                                 wiki=wiki,
                                 edits=edits,
                                 noops=noops,
                                 errors=errors)


def batch_increment_rank_and_show_results(
        wiki: str,
        statement_ids_by_entity_id: Dict[str, List[str]],
        reason: Optional[str],
        session: mwapi.Session,
        custom_summary: Optional[str],
) -> str:
    entities = get_entities(session, statement_ids_by_entity_id.keys())
    edits = {}
    noops = {}
    errors = {}

    for entity_id, statement_ids in statement_ids_by_entity_id.items():
        entity = entities[entity_id]
        base_revision_id = entity['lastrevid']
        statements = entity_statements(entity)
        statements, edited_statements = statements_increment_rank(
            statement_ids,
            statements,
            wiki,
            reason,
        )
        if not edited_statements:
            noops[entity_id] = base_revision_id
            continue
        edited_entity = build_entity(entity_id, statements)
        summary = get_summary_increment_rank(edited_statements,
                                             custom_summary)
        try:
            edits[entity_id] = save_entity(edited_entity,
                                           summary,
                                           base_revision_id,
                                           session)
        except mwapi.errors.APIError as e:
            print('caught error in batch mode:', e, file=sys.stderr)
            errors[entity_id] = e

    wbformat.prefetch_entities(session,
                               flask.g.interface_language_code,
                               statement_ids_by_entity_id.keys())

    return flask.render_template('batch-results.html',
                                 wiki=wiki,
                                 edits=edits,
                                 noops=noops,
                                 errors=errors)


def batch_edit_rank_and_show_results(
        wiki: str,
        commands_by_entity_id: Dict[str, Dict[str, Tuple[str, str]]],
        session: mwapi.Session,
        custom_summary: Optional[str],
) -> str:
    entities = get_entities(session, commands_by_entity_id.keys())
    edits = {}
    noops = {}
    errors = {}

    for entity_id, commands in commands_by_entity_id.items():
        entity = entities[entity_id]
        base_revision_id = entity['lastrevid']
        statements = entity_statements(entity)
        statements, edited_statements = statements_edit_rank(
            commands,
            statements,
            wiki,
        )
        if not edited_statements:
            noops[entity_id] = base_revision_id
            continue
        edited_entity = build_entity(entity_id, statements)
        summary = get_summary_edit_rank(edited_statements,
                                        custom_summary)
        try:
            edits[entity_id] = save_entity(edited_entity,
                                           summary,
                                           base_revision_id,
                                           session)
        except mwapi.errors.APIError as e:
            print('caught error in batch mode:', e, file=sys.stderr)
            errors[entity_id] = e

    wbformat.prefetch_entities(session,
                               flask.g.interface_language_code,
                               commands_by_entity_id.keys())

    return flask.render_template('batch-results.html',
                                 wiki=wiki,
                                 edits=edits,
                                 noops=noops,
                                 errors=errors)
