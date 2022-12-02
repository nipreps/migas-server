FROM python:3.10-slim AS src
RUN pip install -U build pip
RUN apt-get update && \
    apt-get install -y --no-install-recommends git
COPY . /src/migas-server
RUN python -m build /src/migas-server

FROM python:3.10-slim
COPY --from=src /src/migas-server/dist/*.whl .
ENV YARL_NO_EXTENSIONS=1 \
    MULTIDICT_NO_EXTENSIONS=1
RUN python -m pip install --no-cache-dir $( ls *.whl )[test]

ENTRYPOINT ["migas-server"]
