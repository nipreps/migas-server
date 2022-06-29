FROM python:3.10.5-slim-bullseye

COPY . /src

RUN pip install --no-cache-dir /src[test]

ENTRYPOINT ["migas-server"]
