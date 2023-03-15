.PHONY: compose-up compose-down freeze release-gcp

BUILDTYPE=latest
DEPLOYSERVER=uvicorn

compose-up:
	docker compose build --build-arg BUILDTYPE=$(BUILDTYPE) --build-arg DEPLOYSERVER=$(DEPLOYSERVER) --build-arg VERSION=`hatch version`
	docker compose up --detach

compose-down:
	docker compose down

freeze:
	@echo "Freezing requirements"
	pip-compile --extra test -o stable-requirements.txt pyproject.toml --upgrade

release-gcp:
	@echo "Releasing on GCP"
	./deploy/gcp/release-gcp.sh
