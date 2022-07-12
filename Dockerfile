FROM python:3.10.5-slim-bullseye

RUN apt-get update && \
    apt-get install --no-install-recommends -y git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY . /src

ARG GIT_LOCATION=".git"
RUN --mount=source=${GIT_LOCATION},target=.git,type=bind \
    pip install --no-cache-dir /src[test]

ENTRYPOINT ["migas-server"]
