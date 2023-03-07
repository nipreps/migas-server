FROM python:3.10-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
ARG BUILDTYPE=latest
ARG DEPLOYSERVER=uvicorn
ENV YARL_NO_EXTENSIONS=1 \
    MULTIDICT_NO_EXTENSIONS=1 \
    DEPLOYSERVER=${DEPLOYSERVER}
COPY . /src/
WORKDIR /src/
RUN bash deploy/docker/install.sh ${BUILDTYPE} ${DEPLOYSERVER}
ENTRYPOINT ["./deploy/docker/run.sh"]
