# Migas

Usage tracker for your projects!

This is the backend of the migas service.

To play around in the sandbox, visit https://migas-staging.herokuapp.com/graphql in a browser.



## Usage

### Container
Everything needed to run the Migas service is bundled and usable with `docker compose`.

To start up the server:
1) Clone this repository
2) Travel to the root of the repository
3) Run `docker compose up`

### Local
If you want to install and run the server locally, first install the package

```
$ pip install https://github.com/mgxd/migas-server/archive/refs/heads/master.zip
```

* Note: Python 3.10 or higher is required.

Once installed, start the server with `migas-server`.

<details>
<summary>Expand for full options</summary>

```
usage: migas-server [-h] [--host HOST] [--port PORT] [--workers WORKERS] [--reload] [--proxy-headers]

options:
  -h, --help         show this help message and exit
  --host HOST        hostname
  --port PORT        server port
  --workers WORKERS  worker processes
  --reload           Reload app on change (dev only)
  --proxy-headers    Accept incoming proxy headers
  --headers [HEADERS ...]  Custom HTTP response headers as 'Name:Value' pairs
```
</details>

### Requirements

Migas is built with [FastAPI](https://fastapi.tiangolo.com/), [Strawberry](https://strawberry.rocks/), [PostgreSQL](https://www.postgresql.org/) and [Redis](https://redis.com/). Additionally, to run the server, some environmental variables must be set up - see the table below.

| Service | Environmental Variable | Alternatives | Required |
| ------- | ---------------------- | -------------| -------- |
| redis | MIGAS_REDIS_URI | n/a | Yes
| postgres | DATABASE_URL | n/a | Yes
| sqlalchemy | MIGAS_DEBUG | n/a | No


### Runtime Knobs

Migas includes the following environmental variables to allow finer control when processing requests:

| Environmental Variable | Description | Default |
| ---- | ---- | ---- |
| MIGAS_REQUEST_WINDOW | A sliding window for limiting number of queries (in seconds) | 60 |
| MIGAS_REQUESTS_PER_WINDOW | Maximum number of requests per `MIGAS_REQUEST_WINDOW` | 5 |
| MIGAS_MAX_REQUEST_SIZE | Maximum size of request body | 450 |
