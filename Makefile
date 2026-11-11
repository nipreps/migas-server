.PHONY: docker-build compose-up compose-down freeze release-gcp server-test

BUILDTYPE=latest
DEPLOYSERVER=uvicorn
VERSION=$(shell uvx --with hatch-vcs hatch version 2> /dev/null | tail -n1)

docker-build:
	@[ -n "$(VERSION)" ] || { echo "unable to compute version - is uv installed?"; exit 1; }
	docker compose build --build-arg BUILDTYPE=$(BUILDTYPE) --build-arg DEPLOYSERVER=$(DEPLOYSERVER) --build-arg VERSION=$(VERSION)

# --renew-anon-volumes: the server's /src/.venv is an anonymous volume, which
# compose otherwise carries over and would mask a rebuilt image's environment.
compose-up: docker-build
	docker compose up --detach --wait --renew-anon-volumes

compose-down:
	docker compose down

freeze:
	@echo "Freezing requirements"
	pip-compile --extra test -o stable-requirements.txt pyproject.toml --upgrade

release-gcp:
	@echo "Releasing on GCP"
	./deploy/gcp/release-gcp.sh
