# Freshdesk REST service
[![Build Status](https://travis-ci.org/sesam-community/freshdesk-rest.svg?branch=master)](https://travis-ci.org/sesam-community/freshdesk-rest)


This microservice can be used for [Sesam](https://docs.sesam.io/index.html) and [Freshdesk](https://developers.freshdesk.com/api/) integration as source or receiver system.

### Implemented Features:
* pagination
* continuation support (i.e. [Sesam's JSON Pull Protocol](https://docs.sesam.io/json-pull.html)  )
* rate-limit handling
* GET, PUT, POST, DELETE requests
* anonymization of fields
* _id property generation in GET requests


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
| CONFIG_NAME        | DESCRIPTION           | IS_REQUIRED  |DEFAULT_VALUE|
| -------------------|:---------------------:|:------------:|:-----------:|
| freshdesk_domain | Freshdesk domain  | yes | n/a |
| freshdesk_api_path | path for API | no | /api/v2/ |
| freshdesk_filter_call_max_page_size | Maximum allowed number of entities in a filter call | no | 30 |
| freshdesk_filter_call_max_page_no | Maximum allowed number of pages in a filter call | no | 10 |
| freshdesk_apikey | Freshdesk apikey | yes | n/a |
| logging_level | Level value of the logging level for the service (see https://docs.python.org/2/library/logging.html#logging-levels) | no | WARNING |
| properties_to_anonymize_per_uri_template | Dictionary where key are API calls URI template and values are list of object properties to be anonymized | no | {} |
| anonymization_string | the string value used for anonymization of values | no | * |
|generate_sesam_id | Flag to control the generation of _id property. Set "False" to get entities without _id field populated, any other value otherwise | no | True |

##### example configuration in SESAM:

```
{
  "_id": "freshdesk-rest-proxy",
  "type": "system:microservice",
  "docker": {
    "environment": {
      "freshdesk_apikey": "$SECRET(freshdesk-apikey)",
      "freshdesk_domain": "$ENV(freshdesk-domain)"
      "logging_level": "INFO"
    },
    "image": "sesamcommunity/freshdesk-rest:latest",
    "port": 5000
  }
}

```
