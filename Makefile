.PHONY: docker-build compose-up compose-down freeze release-gcp shpg

BUILDTYPE=latest
DEPLOYSERVER=uvicorn
VERSION=$(shell hatch version 2> /dev/null | tail -n1)

docker-build:
	@[ -n "$(VERSION)" ] || { echo "hatch was unable to find version - is it installed?"; exit 1; }
	docker build --rm --tag migas:latest --build-arg BUILDTYPE=$(BUILDTYPE) --build-arg DEPLOYSERVER=$(DEPLOYSERVER) --build-arg VERSION=$(VERSION) .

compose-up: docker-build
	docker compose up --detach

compose-down:
	docker compose down --volumes

freeze:
	@echo "Freezing requirements"
	pip-compile --extra test -o stable-requirements.txt pyproject.toml --upgrade

release-gcp:
	@echo "Releasing on GCP"
	./deploy/gcp/release-gcp.sh

shpg:
	docker exec --user postgres -it $(docker ps -a | grep postgres | awk '{print $1}') sh
