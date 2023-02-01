.PHONY: freeze

freeze:
	@echo "Freezing requirements"
	pip-compile --extra test -o requirements.txt pyproject.toml --upgrade

release-gcp:
	@echo "Releasing on GCP"
	./deploy/gcp/release-gcp.sh
