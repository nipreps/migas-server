import requests

mutation = '''
mutation {
addProject(
p: {
repo: "fmriprep",
owner: "nipreps",
version: "22.0.0",
language: "python",
languageVersion: "3.10.4",
status: error
})}'''

query = 'query { getProjects { name context { user } } }'

r = requests.post('http://0.0.0.0:8000/graphql/', json={'query': mutation})

print(r.json())
