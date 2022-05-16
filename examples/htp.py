"""Stripped down, minimal import way to communicate with server"""

import json
from http.client import HTTPConnection, HTTPSConnection
from urllib.parse import urlparse

mutation = '''
mutation {
addProject(
p: {
repo: "nitransforms",
owner: "nipy",
version: "22.0.0",
language: "python",
languageVersion: "3.10.4",
status: error,
userId: "693f1268-8449-35e9-acc1-eb2315afe6f2"
})}'''

query = 'query { getProjects { name context { user } } }'

url = 'http://0.0.0.0:8000/graphql'
purl = urlparse(url)
# ParseResult(scheme='http', netloc='0.0.0.0:8000', path='/graphql/', params='', query='', fragment='')

Connection = HTTPSConnection if purl.scheme == 'https' else HTTPConnection
body = json.dumps({"query": mutation}).encode("utf-8")

conn = Connection(purl.netloc)
headers = {
    'User-Agent': 'etelemetry/0.0.1',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept': '*/*',
    'Connection': 'keep-alive',
    'Content-Length': len(body),
    'Content-Type': 'application/json',
}

print(f"Length of content: {len(body)}")

conn.connect()
conn.request("POST", purl.path, body, headers)
response = conn.getresponse()
data = response.read().decode()

print(json.loads(data))
