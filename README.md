# Freshdesk REST service
[![Build Status](https://travis-ci.org/sesam-community/freshdesk-rest.svg?branch=master)](https://travis-ci.org/sesam-community/freshdesk-rest)


This microservice can be used for [Sesam](https://docs.sesam.io/index.html) and [Freshdesk](https://developers.freshdesk.com/api/) integration as source or receiver system.

### Implemented Features:
* streaming of response content
* pagination
* continuation support (i.e. [Sesam's JSON Pull Protocol](https://docs.sesam.io/json-pull.html)  )
* rate-limit handling
* GET, PUT, POST, DELETE requests
* _id and _updated property generation in GET requests
* optional sesam callback feature for PUT/POST/DELETE requests. requires both _sesam_url_ and _sesam_node_ to be set


Limitations
* continuation(i.e. Sesam's _since_ parameter) is supported only for date/datetime values. This should suffice for Freshdesk data model.
* [attachments](https://developers.freshdesk.com/api/#attachments) are not supported

### Running locally in a virtual environment
```
  export freshdesk_domain="<freshdesk_domain>"
  export freshdesk_apikey="<freshdesk_apikey>"

  cd freshdesk-rest/service
  virtualenv --python=python3 venv
  . venv/bin/activate
  pip install -r requirements.txt

  python freshdesk-rest.py
   * Running on http://0.0.0.0:5000/ (Press CTRL+C to quit)
   * Restarting with stat
   * Debugger is active!
   * Debugger pin code: 260-787-156
```

The service listens on port 5000 on localhost.

### Running the docker image
```
  docker pull DOCKER_USER/freshdesk-rest:IMAGE_TAG
  docker run -p 5000:5000 --env-file [envlist_file] DOCKER_USER/freshdesk-rest:IMAGE_TAG
```

The service listens on port 5000 on localhost.

### Example calls

##### GET
```
curl -G http://localhost:5000/contacts --data-urlencode "page=1" --data-urlencode "limit=75"
curl -G http://localhost:5000/contacts --data-urlencode "limit=75"
curl -G http://localhost:5000/search/contacts --data-urlencode "query=\"updated_at:>'2017-12-01' AND updated_at:<'2018-03-01'\""
curl -G http://localhost:5000/companies/[company_id]
curl -G http://localhost:5000/tickets --data-urlencode "since=2018-04-30"
curl -G http://localhost:5000/surveys
curl -G http://localhost:5000/surveys/satisfaction_ratings --data-urlencode "since=2017-12-12"
curl -G http://localhost:5000/roles
curl -G http://localhost:5000/groups
curl -G http://localhost:5000/agents
curl -G http://localhost:5000/ticket_fields
curl -G http://localhost:5000/contact_fields

curl -G http://localhost:5000/search/contacts --data-urlencode "since=2017-12-01"
curl -G http://localhost:5000/search/contacts --data-urlencode "since=2017-12-01" --data-urlencode "query=\"updated_at:<'2018-03-01'\""
curl -G http://localhost:5000/search/contacts --data-urlencode "query=\"updated_at:<'2018-03-01'\""
curl -G http://localhost:5000/tickets --data-urlencode "since=2018-12-01"
```
##### POST
```
curl -X POST  http://localhost:5000/contacts -H 'Content-Type: application/json' -d '[json data]'
curl -X POST  http://localhost:5000/companies -H 'Content-Type: application/json' -d '[json data]'
curl -X POST  http://localhost:5000/tickets/[ticket_id]/reply -H 'Content-Type: application/json' -d '[json data]'

curl -X POST  http://localhost:5000/tickets -H 'Content-Type: application/json' -d '[json data]'
curl -X POST  http://localhost:5000/tickets/[ticket_id]/reply -H 'Content-Type: application/json' -d '[json data]'
curl -X POST  http://localhost:5000/tickets/[ticket_id]/reply -H 'Content-Type: application/json' -d '[json data]'

curl -X POST  http://localhost:5000/companies -H 'Content-Type: application/json' -d '{"name": "c", "custom_fields": {"customer_code": "123456"}}'

```
#####  PUT
```
curl -X PUT  http://localhost:5000/companies/[company_id] -H 'Content-Type: application/json' -d '[json data]'
curl -X PUT  http://localhost:5000/contacts/[contact_id] -H 'Content-Type: application/json' -d '{"description": "Test company"}'
```

##### DELETE
```
curl -X DELETE  http://localhost:5000/companies/[company_id]
curl -X DELETE  http://localhost:5000/conversations/[company_id]
```

##### configuration items:

Configuration Items are either of a number or string. Thus, '"' char must be escaped in strings.

| CONFIG_NAME        | DESCRIPTION           | IS_REQUIRED  |DEFAULT_VALUE|
| -------------------|:---------------------:|:------------:|:-----------:|
| port | port number for the service  | no | 5000 |
| freshdesk_domain | Freshdesk domain  | yes | n/a |
| freshdesk_api_path | path for API | no | "/api/v2/" |
| freshdesk_filter_call_max_page_size | Maximum allowed number of entities in a filter call | no | 30 |
| freshdesk_filter_call_max_page_no | Maximum allowed number of pages in a filter call | no | 10 |
| freshdesk_apikey | Freshdesk apikey | yes | n/a |
| logging_level | Level value of the logging level for the service (see https://docs.python.org/2/library/logging.html#logging-levels) | no | "WARNING" |
| threshold_delayed_response | numeric threshold for rate-limit handling. Specify a value between 0 and 1 for ratio comparison, any other value for absolute comparison. Once passed streams content will be delayed by delay_responses_by_seconds secs. Checked once per page.  | no | 0.3 |
| threshold_reject_requests | numeric threshold for rate-limit handling. Specify a value between 0 and 1 for ratio comparison, any other value for absolute comparison. Once passed 3 things might happen: 1-new requests will be either rejected 2-ongoing streams will be stopped if it is an incremental fetch 3-Response will be disrupted it it is a full scan fetch. Checked once per page.  | no | 0.1 |
| delay_responses_by_seconds | duration of delay in seconds when threshold_delayed_response reached | no | 60 |
| sesam_url | sesam url e.g. _https://datahub-1426e5f8.sesam.cloud_  | no | n/a |
| sesam_jwt | sesam_jwt for the sesam node | no | n/a |


##### example configuration in SESAM:

minimal:
```
{
  "_id": "freshdesk-rest-proxy",
  "type": "system:microservice",
  "docker": {
    "environment": {
      "freshdesk_apikey": "$SECRET(freshdesk-apikey)",
      "freshdesk_domain": "$ENV(freshdesk-domain)"
    },
    "image": "sesamcommunity/freshdesk-rest:latest",
    "port": 5000
  }
}

```
maximal:

```
{
  "_id": "freshdesk-rest-proxy",
  "type": "system:microservice",
  "docker": {
    "environment": {
      "port": 5000,
      "freshdesk_apikey": "$SECRET(freshdesk-apikey)",
      "freshdesk_domain": "$ENV(freshdesk-domain)"
      "freshdesk_api_path": "/api/v2/",
      "freshdesk_filter_call_max_page_size": 30,
      "freshdesk_filter_call_max_page_no": 10,
      "logging_level": "DEBUG",
      "threshold_delayed_response": 2000
      "threshold_reject_requests": 1000,
      "delay_responses_by_seconds": 30
      "sesam_url": "https://my-sesam-subscription.sesam.cloud",
      "sesam_jwt": "mysesamjwt"
    },
    "image": "sesamcommunity/freshdesk-rest:latest",
    "port": 5000
  }
}

```
