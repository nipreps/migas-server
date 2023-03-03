.PHONY: compose-up freeze release-gcp

BUILDTYPE=latest

compose-up:
	docker compose build --build-arg BUILDTYPE=$(BUILDTYPE)
	docker compose up

freeze:
	@echo "Freezing requirements"
	pip-compile --extra test -o requirements.txt pyproject.toml --upgrade

release-gcp:
	@echo "Releasing on GCP"
	./deploy/gcp/release-gcp.sh
