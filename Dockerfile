FROM python:3.10-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
ENV YARL_NO_EXTENSIONS=1 \
    MULTIDICT_NO_EXTENSIONS=1
COPY . /src/
WORKDIR /src/
ARG BUILDTYPE=latest
RUN bash deploy/docker/install.sh ${BUILDTYPE}
CMD ["./deploy/docker/run.sh"]
