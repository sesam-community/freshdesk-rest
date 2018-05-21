from flask import Flask, request, Response, abort, redirect
import os
import requests
import logging
import json
import re
import sys
from time import sleep

app = Flask(__name__)
format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logger = logging.getLogger('freshdesk-rest-service')

# Log to stdout
stdout_handler = logging.StreamHandler()
stdout_handler.setFormatter(logging.Formatter(format_string))
logger.addHandler(stdout_handler)
logger.setLevel(os.getenv("logging_level", logging.WARNING))

FRESHDESK_DOMAIN = os.getenv("freshdesk_domain")
FRESHDESK_API_PATH = os.getenv("freshdesk_api_path", "/api/v2/")
FRESHDESK_FILTER_CALL_MAX_PAGE_SIZE = int(
    os.getenv("freshdesk_filter_call_max_page_size", 30))
FRESHDESK_FILTER_CALL_MAX_PAGE_NO = int(
    os.getenv("freshdesk_filter_call_max_page_no", 10))
FRESHDESK_APIKEY = os.getenv('freshdesk_apikey')
FRESHDESK_HEADERS = {'Content-Type': 'application/json'}
FRESHDESK_URL_ROOT = str(FRESHDESK_DOMAIN) + str(FRESHDESK_API_PATH)

PAGE_SIZE = int(os.getenv("page_size", 100))
DO_GENERATE_SESAM_ID = bool(os.getenv("generate_sesam_id", "True") != "False")

BLACKLIST_UPDATED_TOKEN_GENERATION = ["surveys"]
PROPERTIES_TO_ANONYMIZE_PER_URI_TEMPLATE = json.loads(os.environ.get(
    'properties_to_anonymize_per_uri_template', "{}").replace("'", "\""))
ANONYMIZATION_STRING = os.environ.get('anonymization_string', "*")
VALID_RESPONSE_COMBOS = [("GET", 200), ("POST", 201),
                         ("PUT", 200), ("DELETE", 204)]

required_vars = [ FRESHDESK_DOMAIN, FRESHDESK_APIKEY]
for var in required_vars:
    if var is None or not var:
        raise SystemExit("Freshdesk-rest service cannot be started:Not all mandatory variables are initialized")

def get_uri_template(path):
    return re.sub(r"\d+", r"_id_", path)

# Sesam Json Pull Protocol is transformed to Freshdesk API headers
# Freshdesk rules:
#   max page size is 30 for "search" calls, 100 otherwise
#   "search" calls accepts only following params: query, per_page, page


def get_freshdesk_req_params(path, service_params):
    freshdesk_req_params = service_params
    since_support_config = {
        'tickets': {'param': 'updated_since', 'operator': '='},
        'surveys/satisfaction_ratings': {'param': 'created_since',
                'operator': '='},
        'search/companies': {'param': 'updated_at', 'operator': ':>'},
        'search/contacts': {'param': 'updated_at', 'operator': ':>'}
        }

    uri_template = get_uri_template(path)
    if "search/" not in uri_template:
        freshdesk_req_params.setdefault(
            "per_page", service_params.get("limit", PAGE_SIZE))

    if "limit" in freshdesk_req_params:
        del freshdesk_req_params["limit"]

    if service_params.get("since") is not None and uri_template in since_support_config:
        if "search/" in uri_template:
            since_query_segment = since_support_config[uri_template]["param"] + since_support_config[uri_template]["operator"] + "'" + re.sub(
                r"T.*", r"", freshdesk_req_params["since"]) + "'"
            if freshdesk_req_params.get("query", None) is not None:
                freshdesk_req_params["query"] = "\"(" + service_params.get(
                    "query").replace("\"", "") + ") AND " + since_query_segment + "\""
            else:
                freshdesk_req_params["query"] = "\"" + \
                    since_query_segment + "\""
        else:
            freshdesk_req_params[since_support_config[uri_template]
                                 ["param"]] = service_params.get("since")
        del freshdesk_req_params["since"]

    return freshdesk_req_params


def call_service(url, params, json):
    logger.info("Issuing a %s call with url=%s, with param list=%s, headers=%s",
                request.method, url, params, FRESHDESK_HEADERS)
    freshdesk_response = requests.request(method=request.method, url=url, headers=FRESHDESK_HEADERS, auth=(
        FRESHDESK_APIKEY, 'X'), params=params, json=json)
    # status code 429 is returned when rate-limit is achived, and returns retry-after value
    if freshdesk_response.status_code in [429]:
        if freshdesk_response.headers.get('Retry-After') is not None:
            retry_after = freshdesk_response.headers.get('Retry-After')
        logger.error("sleeping for %s seconds", retry_after)
        sleep(float(retry_after))
    elif (request.method, freshdesk_response.status_code) not in VALID_RESPONSE_COMBOS:
        logger.error("Unexpected response status code=%d, request-ID=%s, response text=%s" %
                     (freshdesk_response.status_code, freshdesk_response.headers.get('X-Request-Id'), freshdesk_response.text))

    return freshdesk_response


# fetches data for any GET request, supports pagination
def fetch_data(path, freshdesk_req_params):
    base_url = FRESHDESK_URL_ROOT + path
    page_counter = 0

    data_to_return = []
    base_url_next_page = base_url
    uri_template = get_uri_template(path)
    while base_url_next_page is not None:
        page_counter += 1
        freshdesk_response = call_service(
            base_url_next_page, freshdesk_req_params, None)
        if freshdesk_response.status_code != 200:
            return freshdesk_response.text, freshdesk_response.status_code
        response_json = freshdesk_response.json()
        # search calls return entites in "results" property
        if "search/" in uri_template:
            data_from_freshdesk = response_json.get("results")
            total_object_count = response_json.get("total")
            if page_counter == FRESHDESK_FILTER_CALL_MAX_PAGE_NO:
                logger.error("MAX page number reached before fetching all objects: total_object_count=%s, FRESHDESK_FILTER_CALL_MAX_PAGE_NO=%s, page_counter=%s" % (
                    total_object_count, FRESHDESK_FILTER_CALL_MAX_PAGE_NO, page_counter))
                return {"message": "MAX page number reached before fetching all objects"}, 500
            if total_object_count > page_counter * FRESHDESK_FILTER_CALL_MAX_PAGE_SIZE:
                freshdesk_req_params["page"] = page_counter + 1
            else:
                base_url_next_page = None
        else:
            data_from_freshdesk = response_json
            link_text = freshdesk_response.headers.get("Link")
            if link_text is not None and request.args.get("page") is None:
                base_url_next_page = link_text[1:link_text.index(">")]
            else:
                base_url_next_page = None
        if isinstance(data_from_freshdesk, dict):
            data_to_return = data_from_freshdesk
            if DO_GENERATE_SESAM_ID:
                data_to_return["_id"] = str(data_to_return["id"])
            if path not in BLACKLIST_UPDATED_TOKEN_GENERATION:
                data_to_return["_updated"] = data_to_return["updated_at"]
        elif isinstance(data_from_freshdesk, list):
            if DO_GENERATE_SESAM_ID:
                for entity in data_from_freshdesk:
                    entity["_id"] = str(entity["id"])
            if path in BLACKLIST_UPDATED_TOKEN_GENERATION:
                data_to_return.extend(data_from_freshdesk)
            else:
                for entity in data_from_freshdesk:
                    entity["_updated"] = entity["updated_at"]
                    data_to_return.append(entity)

    if uri_template in PROPERTIES_TO_ANONYMIZE_PER_URI_TEMPLATE:
        fields_to_anonymize = PROPERTIES_TO_ANONYMIZE_PER_URI_TEMPLATE[uri_template]
        for entity in data_from_freshdesk:
            for prop in fields_to_anonymize:
                entity[prop] = ANONYMIZATION_STRING

    # for sub objects, it is only page size that should be sent
    freshdesk_req_params = {"per_page": 100}
    # fetch underlying entity types for the resultset
    if uri_template == "solutions/categories":
        for entity in data_to_return:
            entity["folders"], response_code = fetch_data(
                uri_template + "/" + str(entity["id"]) + "/folders", freshdesk_req_params)
    elif uri_template == "solutions/categories/_id_/folders":
        for entity in data_to_return:
            entity["articles"], response_code = fetch_data(
                "solutions/folders/" + str(entity["id"]) + "/articles", freshdesk_req_params)
    elif uri_template in ["tickets", "search/tickets"]:
        for entity in data_to_return:
            entity["conversations"], response_code = fetch_data(
                "tickets/" + str(entity["id"]) + "/conversations", freshdesk_req_params)
            entity["time_entries"], response_code = fetch_data(
                "tickets/" + str(entity["id"]) + "/time_entries", freshdesk_req_params)

    logger.debug("returning %s entities" % len(data_to_return))

    return data_to_return, 200


@app.route("/<path:path>", methods=["GET"])
def get(path):
    freshdesk_req_params = get_freshdesk_req_params(
        path, request.args.to_dict(True))
    data_to_return, status_code = fetch_data(path, freshdesk_req_params)
    return Response(response=json.dumps(data_to_return), status=status_code, mimetype='application/json', content_type='application/json; charset=utf-8')


@app.route("/<path:path>", methods=["POST", "PUT", "DELETE"])
def post(path):
    base_url = FRESHDESK_URL_ROOT + path

    freshdesk_req_params = get_freshdesk_req_params(
        base_url, request.args.to_dict(True))
    freshdesk_response = call_service(
        base_url, freshdesk_req_params, request.get_json())
    return Response(response=freshdesk_response, status=freshdesk_response.status_code, mimetype='application/json', content_type='application/json; charset=utf-8')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=os.getenv('port', 5000))
