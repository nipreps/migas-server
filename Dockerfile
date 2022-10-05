FROM python:slim AS src
RUN pip install build
RUN apt-get update && \
    apt-get install -y --no-install-recommends git
COPY . /src/migas-server
RUN python -m build /src/migas-server

FROM python:slim
COPY --from=src /src/migas-server/dist/*.whl .
RUN python -m pip install --no-cache-dir $( ls *.whl )[test]

ENTRYPOINT ["migas-server"]
