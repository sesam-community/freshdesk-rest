from flask import Flask, request, Response, stream_with_context
import os
import requests
import logging
import json
import re
import sys
import traceback
import types
from time import sleep
from datetime import datetime, timedelta
import logger as log

app = Flask(__name__)

ENV_DEFAULTS = {
    'port':
        5000,
    'freshdesk_api_path':
        '/api/v2/',
    'freshdesk_filter_call_max_page_size':
        30,
    'freshdesk_filter_call_max_page_no':
        10,
    'sesam_callback_config':
        '[ \
        { \
            "uri_templates" : ["companies/_id_", "companies"], \
            "config" : \
                { \
                    "pipe_id": "freshdesk-company-receiver" \
                } \
        } \
      ]',
    'generate_sesam_id':
        'True',
    'logging_level':
        'WARNING',
    'threshold_delayed_response':
        '0.3',
    'threshold_reject_requests':
        '0.1',
    'delay_responses_by_seconds':
        60
}
logger = log.init_logger('freshdesk-rest-service',
                         os.getenv('logging_level', ENV_DEFAULTS.get('logging_level')))
FRESHDESK_DOMAIN = os.getenv('freshdesk_domain')
FRESHDESK_API_PATH = os.getenv('freshdesk_api_path',
                               ENV_DEFAULTS.get('freshdesk_api_path'))
FRESHDESK_FILTER_CALL_MAX_PAGE_SIZE = int(
    os.getenv('freshdesk_filter_call_max_page_size',
              ENV_DEFAULTS.get('freshdesk_filter_call_max_page_size')))
FRESHDESK_FILTER_CALL_MAX_PAGE_NO = int(
    os.getenv('freshdesk_filter_call_max_page_no',
              ENV_DEFAULTS.get('freshdesk_filter_call_max_page_no')))
FRESHDESK_APIKEY = os.getenv('freshdesk_apikey')
FRESHDESK_HEADERS = {'Content-Type': 'application/json'}
FRESHDESK_URL_ROOT = str(FRESHDESK_DOMAIN) + str(FRESHDESK_API_PATH)

SECONDS_TO_SHIFT_SINCE_VALUE_BY = int(
    os.getenv('seconds_to_shift_since_value_by', 0))

SESAM_URL = os.getenv('sesam_url', None)
SESAM_JWT = os.getenv('sesam_jwt', None)
SESAM_CALLBACK_CONFIG = json.loads(
    os.getenv('sesam_callback_config',
              ENV_DEFAULTS.get('sesam_callback_config')))
DO_GENERATE_SESAM_ID = bool(
    os.getenv('generate_sesam_id',
              ENV_DEFAULTS.get('generate_sesam_id')) != 'False')

RATE_LIMIT_HANDLING_THRESHOLDS = [
    ('REJECT_REQUESTS',
     float(
         os.environ.get('threshold_reject_requests',
                        ENV_DEFAULTS.get('threshold_reject_requests')))),
    ('DELAYED_RESPONSE',
     float(
         os.environ.get('threshold_delayed_response',
                        ENV_DEFAULTS.get('threshold_delayed_response'))))
]

DELAY_RESPONSES_BY_SECONDS = int(
    os.environ.get('delay_responses_by_seconds',
                   ENV_DEFAULTS.get('delay_responses_by_seconds')))

required_values = [FRESHDESK_DOMAIN, FRESHDESK_APIKEY]
for value in required_values:
    if not value or re.match('^\$\(.*\)$', value):
        raise SystemExit(
            'Freshdesk-rest service cannot be started:Not all mandatory variables are initialized'
        )

BLACKLIST_UPDATED_TOKEN_GENERATION = ['surveys']
FRESHDESK_HIERARCHY_URI_CONFIG = [
    {
        'parent_uri_template': ['solutions/categories'],
        'children_config': [{
            'child_uri_template': 'solutions/categories/_id_/folders',
            'target_property': 'folders'
        }]
    },
    {
        'parent_uri_template': ['solutions/categories/_id_/folders'],
        'children_config': [{
            'child_uri_template': 'solutions/folders/_id_/articles',
            'target_property': 'articles'
        }]
    },
    {
        'parent_uri_template': ['tickets',
                                'tickets/_id_',
                                'search/tickets'],
        'children_config': [
            {
                'child_uri_template': 'tickets/_id_/time_entries',
                'target_property': 'time_entries'
            },
            {
                'child_uri_template': 'tickets/_id_/conversations',
                'target_property': 'conversations'
            }
        ]
    }
]


# fd_param, operator, full_load_since_value fields are defined either to overcome
# or to make full runs for search/XXX path valid
SINCE_SUPPORT_CONFIG = {
    'tickets': {
        'fd_param': 'updated_since',
        'operator': '=',
        'full_load_since_value': '1970-01-01T00:00:00Z',
        'datetime_format': '%Y-%m-%dT%H:%M:%SZ'
    },
    'contacts': {
        'fd_param': '_updated_since',
        'operator': '=',
        'full_load_since_value': None,
        'datetime_format': '%Y-%m-%dT%H:%M:%SZ'
    },
    'surveys/satisfaction_ratings': {
        'fd_param': 'created_since',
        'operator': '=',
        'full_load_since_value': '1970-01-01T00:00:00Z',
        'datetime_format': '%Y-%m-%dT%H:%M:%SZ'
    },
    'search/companies': {
        'fd_param': 'updated_at',
        'operator': ':>',
        'full_load_since_value': '1970-01-01',
        'datetime_format': '%Y-%m-%d'
    },
    'search/contacts': {
        'fd_param': 'updated_at',
        'operator': ':>',
        'full_load_since_value': '1970-01-01',
        'datetime_format': '%Y-%m-%d'
    }
}

VALID_RESPONSE_COMBOS = [('GET',
                          200),
                         ('POST',
                          201),
                         ('PUT',
                          200),
                         ('DELETE',
                          204)]

FRESHDESK_MAX_PAGE_SIZE = 100


def get_uri_template(path):
    return re.sub(r'/$', r'', re.sub(r'\d+', r'_id_', path)), re.sub(
        r'[a-zA-Z\/]+', r'', path)


def log_exception():
    exc_type, exc_value, exc_traceback = sys.exc_info()
    logger.error(
        traceback.format_exception(exc_type,
                                   exc_value,
                                   exc_traceback))


def to_sesam_entity(in_dict, uri_template):
    if DO_GENERATE_SESAM_ID:
        in_dict['_id'] = str(in_dict['id'])
    if uri_template not in BLACKLIST_UPDATED_TOKEN_GENERATION:
        in_dict['_updated'] = str(in_dict['updated_at'])
    return in_dict


def sesam_callback(method, config, resource_id, json_data, uri_template):
    if not SESAM_URL or not SESAM_JWT:
        return
    callback_url = SESAM_URL + '/api/receivers/' + \
        config['pipe_id'] + '/entities'
    headers = {
        'Authorization': 'bearer ' + SESAM_JWT,
        'Accept': 'application/problem+json',
        'content-type': 'application/json'
    }
    entity_to_post = {}
    if method == 'DELETE':
        entity_to_post['_id'] = resource_id
        entity_to_post['_deleted'] = True
    else:
        entity_to_post = to_sesam_entity(json_data, uri_template)
    if entity_to_post:
        logger.debug(
            'issuing a %s call url=%s, json=%s' % (method,
                                                   callback_url + '/entity',
                                                   entity_to_post))
        sesam_response = requests.post(
            url=callback_url,
            headers=headers,
            json=entity_to_post)
        if sesam_response.status_code != 200:
            logger.warn('cannot post entity \'%s\' to \'%s\' : %s' %
                        (entity_to_post.get('_id'),
                         callback_url,
                         sesam_response.text))


# Sesam Json Pull Protocol is transformed to Freshdesk API headers
# Freshdesk rules:
#   max page size is 30 for 'search' calls, 100 otherwise
#   'search' calls accepts only following params: query, per_page, page


def get_params(path, params):
    execution_params = {'is_full_scan': True, 'is_recursed': False,
                        'active_rate_limit_handling_policy': None}
    uri_template, freshdesk_resource_id = get_uri_template(path)
    if 'search/' not in uri_template and '_id_' not in uri_template:
        params.setdefault(
            'per_page',
            min(
                int(params.get('limit',
                               FRESHDESK_MAX_PAGE_SIZE)),
                int(params.get('page_size',
                               FRESHDESK_MAX_PAGE_SIZE))))

    if uri_template in SINCE_SUPPORT_CONFIG:
        config = SINCE_SUPPORT_CONFIG[uri_template]
        since_value = params.get('since')
        if since_value:
            execution_params['is_full_scan'] = False
            if SECONDS_TO_SHIFT_SINCE_VALUE_BY > 0:
                since_date = datetime.strptime(
                    since_value, config['datetime_format'])
                since_date = since_date - \
                    timedelta(seconds=SECONDS_TO_SHIFT_SINCE_VALUE_BY)
                since_value = datetime.strftime(
                    since_date, config['datetime_format'])
        else:
            since_value = config['full_load_since_value']
        if since_value:
            if 'search/' in uri_template:
                since_query_segment = config['fd_param'] + config['operator'] + '\'' + re.sub(
                    r'T.*',
                    r'',
                    since_value) + '\''
                if params.get('query', None) is not None:
                    params['query'] = '\"(' + params.get('query').replace(
                        '\"',
                        '') + ') AND ' + since_query_segment + '\"'
                else:
                    params['query'] = '\"' + since_query_segment + '\"'
            else:
                params[config['fd_param']] = since_value

    # delete params that are specific to SESAM Pull Protocal
    for param in ['limit', 'page_size', 'since']:
        if param in params:
            del params[param]
    return params, execution_params


def call_service(freshdesk_request_session, method, url, params, json_data):
    logger.debug(
        'Issuing a %s call with url=%s, with param list=%s, headers=%s',
        method,
        url,
        params,
        FRESHDESK_HEADERS)
    freshdesk_response = freshdesk_request_session.request(
        method=method,
        url=url,
        params=params,
        json=json_data)
    # status code 429 is returned when rate-limit is achived, and returns retry-after value
    if freshdesk_response.status_code in [429]:
        seconds_multiplier = 1
        if freshdesk_response.headers.get('Retry-After') is not None:
            retry_after = freshdesk_response.headers.get('Retry-After')
            if retry_after[-4:] == " min":
                retry_after = retry_after[:-4]
                seconds_multiplier = 60
        logger.error('sleeping for %s seconds', retry_after)
        sleep(float(retry_after) * seconds_multiplier)
    elif (method, freshdesk_response.status_code) not in VALID_RESPONSE_COMBOS:
        logger.error(
            'Unexpected response status code=%d, request-ID=%s, response text=%s'
            % (freshdesk_response.status_code,
               freshdesk_response.headers.get('X-Request-Id'),
               freshdesk_response.text))

    elif method in ['PUT', 'POST', 'DELETE']:
        uri_template, freshdesk_resource_id = get_uri_template(
            url.replace(FRESHDESK_URL_ROOT, ''))
        json_data_to_sesam = {}
        if method != 'DELETE':
            json_data_to_sesam = freshdesk_response.json()
        for callback_config in SESAM_CALLBACK_CONFIG:
            if uri_template in callback_config['uri_templates']:
                sesam_callback(method,
                               callback_config['config'],
                               freshdesk_resource_id,
                               json_data_to_sesam,
                               uri_template)
    return freshdesk_response


# streams data for any GET request, supports pagination
def fetch_data(freshdesk_request_session,
               path,
               freshdesk_req_params,
               execution_params):

    def update_execution_params(freshdesk_req_params, execution_params):
        execution_params['is_hierarchy_on'] = freshdesk_req_params.get(
            'filter',
            '').lower() not in ['deleted',
                                'spam']

    def check_rate_limit(rate_limit_remaining,
                         rate_limit_total,
                         execution_params):
        policy = 'DEFAULT'
        policy_threshold = None
        if not execution_params.get('is_recursed') and rate_limit_remaining:
            current_ratio = int(rate_limit_remaining) / float(rate_limit_total)
            for tmp_policy, tmp_threshold in RATE_LIMIT_HANDLING_THRESHOLDS:
                if (tmp_threshold < 1
                        and current_ratio <
                        tmp_threshold) or (
                            tmp_threshold > 1
                            and int(rate_limit_remaining) < tmp_threshold):
                    policy = tmp_policy
                    policy_threshold = tmp_threshold
                    break
            if execution_params.get('active_rate_limit_handling_policy') != policy and not (
                    policy == 'DEFAULT'
                    and not execution_params.get('active_rate_limit_handling_policy')):
                logger.warning(
                    'Applying %s policy after checking remaining rate-limit against the threshold value (%s/%s=%s vs %s)'
                    % (policy,
                       rate_limit_remaining,
                       rate_limit_total,
                       int(rate_limit_remaining) / int(rate_limit_total),
                       policy_threshold))
                execution_params['active_rate_limit_handling_policy'] = policy
            if policy == 'DELAYED_RESPONSE':
                sleep(DELAY_RESPONSES_BY_SECONDS)
            elif policy == 'REJECT_REQUESTS':
                if path in SINCE_SUPPORT_CONFIG and not execution_params['is_full_scan']:
                    raise StopIteration
                else:
                    raise RuntimeError(
                        'Request rejected. Rate-limit reamining is less then the THRESHOLD_REJECT_REQUESTS'
                    )
        return

    base_url = FRESHDESK_URL_ROOT + path
    base_url_next_page = base_url
    update_execution_params(freshdesk_req_params, execution_params)
    page_counter = 0
    total_enties = 0
    uri_template, freshdesk_resource_id = get_uri_template(path)
    try:
        is_first_yield = True
        yield '['
        while base_url_next_page is not None:
            paged_entities = []
            page_counter += 1
            freshdesk_response = call_service(freshdesk_request_session,
                                              'GET',
                                              base_url_next_page,
                                              freshdesk_req_params,
                                              None)
            if freshdesk_response.status_code != 200:
                raise AssertionError(freshdesk_response.text)
            check_rate_limit(
                freshdesk_response.headers.get('X-Ratelimit-Remaining'),
                freshdesk_response.headers.get('X-Ratelimit-Total'),
                execution_params)
            response_json = freshdesk_response.json()
            # search calls return entites in 'results' property
            if 'search/' in uri_template:
                data_from_freshdesk = response_json.get('results')
                total_object_count = response_json.get('total')
                if page_counter == FRESHDESK_FILTER_CALL_MAX_PAGE_NO:
                    logger.error(
                        'MAX page number reached before fetching all objects: total_object_count=%s, FRESHDESK_FILTER_CALL_MAX_PAGE_NO=%s, page_counter=%s'
                        % (total_object_count,
                           FRESHDESK_FILTER_CALL_MAX_PAGE_NO,
                           page_counter))
                    raise AssertionError(
                        'MAX page number reached before fetching all objects')
                if total_object_count > page_counter * FRESHDESK_FILTER_CALL_MAX_PAGE_SIZE:
                    freshdesk_req_params['page'] = page_counter + 1
                else:
                    base_url_next_page = None
            else:
                data_from_freshdesk = response_json
                link_text = freshdesk_response.headers.get('Link')
                if link_text is not None and 'page' not in freshdesk_req_params:
                    base_url_next_page = link_text[1:link_text.index('>')]
                else:
                    base_url_next_page = None
            if isinstance(data_from_freshdesk, dict):
                paged_entities.append(
                    to_sesam_entity(data_from_freshdesk,
                                    uri_template))
            elif isinstance(data_from_freshdesk, list):
                for entity in data_from_freshdesk:
                    paged_entities.append(
                        to_sesam_entity(entity,
                                        uri_template))

            # fetch underlying entity types for the resultset
            if execution_params.get('is_hierarchy_on'):
                for uri_hierarchy in FRESHDESK_HIERARCHY_URI_CONFIG:
                    if uri_template in uri_hierarchy.get('parent_uri_template'):
                        for child_config in uri_hierarchy.get('children_config'):
                            for entity in paged_entities:
                                uri = re.sub(
                                    r'_id_',
                                    str(entity.get('id')),
                                    child_config.get('child_uri_template'))
                                children_objects = ''
                                execution_params['is_recursed'] = True
                                for child in fetch_data(
                                        freshdesk_request_session,
                                        uri,
                                    {'per_page': FRESHDESK_MAX_PAGE_SIZE},
                                        execution_params):
                                    children_objects += child
                                entity[child_config.get(
                                    'target_property')] = json.loads(
                                        children_objects)
            total_enties += len(paged_entities)
            for data in paged_entities:
                if not is_first_yield:
                    yield ','
                else:
                    is_first_yield = False
                yield json.dumps(data)
            check_rate_limit(
                freshdesk_response.headers.get('X-Ratelimit-Remaining'),
                freshdesk_response.headers.get('X-Ratelimit-Total'), execution_params)

    except StopIteration:
        None
    except Exception as err:
        log_exception()
        yield '500 - encountered error'
    finally:
        yield ']'
    logger.debug('returning %s entities' % total_enties)


def get_freshdesk_session():
    session = requests.Session()
    session.auth = (FRESHDESK_APIKEY, 'X')
    session.headers = FRESHDESK_HEADERS
    return session


def create_response(msg_text, status_code, content_type='application/json; charset=utf-8'):
    return Response(
        response=json.dumps({
            'message': msg_text
        }),
        status=status_code,
        content_type=content_type)


@app.route('/<path:path>', methods=['GET'])
def get(path):
    try:
        freshdesk_req_params, execution_params = get_params(
            path,
            request.args.to_dict(True))
        with get_freshdesk_session() as freshdesk_request_session:
            return Response(
                response=fetch_data(freshdesk_request_session,
                                    path,
                                    freshdesk_req_params,
                                    execution_params),
                content_type='application/json; charset=utf-8')
    except Exception as err:
        log_exception()
        return create_response(str(err), 500)


@app.route('/<path:path>', methods=['POST', 'PUT', 'DELETE'])
def push(path):
    try:
        base_url = FRESHDESK_URL_ROOT + path
        freshdesk_req_params, is_full_scan = get_params(
            base_url,
            request.args.to_dict(True))
        with get_freshdesk_session() as freshdesk_request_session:
            freshdesk_response = call_service(freshdesk_request_session,
                                              request.method,
                                              base_url,
                                              freshdesk_req_params,
                                              request.get_json())
        return Response(
            response=freshdesk_response,
            status=freshdesk_response.status_code,
            mimetype='application/json',
            content_type='application/json; charset=utf-8')
    except Exception as err:
        log_exception()
        return return create_response(str(err), 500)


if __name__ == '__main__':
    if os.environ.get('WEBFRAMEWORK', '').lower() == 'flask':
        app.run(debug=True, host='0.0.0.0', port=int(
            os.environ.get('PORT', 5000)))
    else:
        import cherrypy

        app = log.add_access_logger(app, logger)
        cherrypy.tree.graft(app, '/')

        # Set the configuration of the web server to production mode
        cherrypy.config.update({
            'environment': 'production',
            'engine.autoreload_on': False,
            'log.screen': True,
            'server.socket_port': int(os.environ.get("PORT", 5000)),
            'server.socket_host': '0.0.0.0'
        })

        # Start the CherryPy WSGI web server
        cherrypy.engine.start()
        cherrypy.engine.block()
