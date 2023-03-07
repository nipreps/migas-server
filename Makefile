.PHONY: compose-up freeze release-gcp

BUILDTYPE=latest
DEPLOYSERVER=uvicorn

compose-up:
	docker compose build --build-arg BUILDTYPE=$(BUILDTYPE) --build-arg DEPLOYSERVER=$(DEPLOYSERVER)
	docker compose up

freeze:
	@echo "Freezing requirements"
	pip-compile --extra test -o requirements.txt pyproject.toml --upgrade

release-gcp:
	@echo "Releasing on GCP"
	./deploy/gcp/release-gcp.sh
