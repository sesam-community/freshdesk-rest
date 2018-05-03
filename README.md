# CVpartner REST service
[![Build Status](https://travis-ci.org/sesam-community/cvpartner-rest.svg?branch=master)](https://travis-ci.org/sesam-community/cvpartner-rest)

A small microservice to get entities from a REST api.

This microservice needs information about path to the url of the next page (more in example config).


##### RETURNED example paged-entity
```
[
    {
        "id":"2",
        "foo": "bar"
    },
    {
        "id":"3",
        "foo": "baz"
    }
]
```

##### GET example paged-entity - pipe config
```
[
    "_id": "cvpartner-users",
    "type": "pipe",
    "source": {
        "type": "json",
        "system": "cvpartner",
        "url": "/users"
    }
]
```


##### Example result from GET method
```
{
  "href": "http://foo.com/api/v1/users",
    "values": [
    {
      "id": "1",
      "cv_id": "2",
      "name": "Ashkan",
      "custom_tags": [
        "595a082e77fe09263b7fea20",
        "5954f44d3a4e6107feaea292",
        "5954f4a159264807599b31c2"
      ],
      "skills": [
        "58f756f4502bdb084adaddb4",
        "58f7785b502bdb07f8dade23",
        "594447d938cf5f0ab3315a98",
        "59aea857aca9200810994931"
      ],
      "customers": [
        "5825b3072c04d6206f27f005"
      ],
      "industries": []
    }
  ],
  "total": 2262,
  "next": {
    "href": "http://foo.com/api/v1/users?limit=100&offset=100"
  }
}
```
This will result into returned entities:
```
[
    {
      "id": "1",
      "cv_id": "2",
      "name": "Ashkan",
      "custom_tags": [
        "595a082e77fe09263b7fea20",
        "5954f44d3a4e6107feaea292",
        "5954f4a159264807599b31c2"
      ],
      "skills": [
        "58f756f4502bdb084adaddb4",
        "58f7785b502bdb07f8dade23",
        "594447d938cf5f0ab3315a98",
        "59aea857aca9200810994931"
      ],
      "customers": [
        "5825b3072c04d6206f27f005"
      ],
      "industries": []
    }
]
```


##### POST example paged-entity - pipe config
```
[
    {
        "_id": "foo",
        "post_url": "v3/cvs/:user_id/:cv_id"
    }
]
```

Use http_transform to get data from service that has special urls

##### Example configuration:

```
{
  "_id": "cvpartner",
  "type": "system:microservice",
  "docker": {
    "environment": {
      "base_url": "https://some-rest-service.com/v1/",
      "next_page": "next.href",
      "entities_path": "values", #in which property your entities reside in the result from GET
      "headers": "{'Accept':'application/json', 'Authorization':'$SECRET(token)'}",
      "sleep": "0.400", #sleep for 400 miliseconds between each rest call
      "post_url": "post_url" #the property that contains the url to call
    },
    "image": "sesamcommunity/cvpartner-rest:latest",
    "port": 5000
  }
}
```

