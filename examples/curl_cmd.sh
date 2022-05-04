#!/bin/bash

curl 'http://0.0.0.0:8000/graphql' \
 -X POST \
 -H 'Accept: application/json' \
 -H 'Content-Type: application/json' \
 -D - \
 --data '{
 "query": "mutation { addProject(name:\"fail\", version:\"1.2\", language:\"python\", languageVersion: \"3.6\") {name}}"
 }'
