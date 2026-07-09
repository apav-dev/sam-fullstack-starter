# SAM BuildMethod: makefile targets.
# deploy.sh copies this file (plus api/ and requirements.txt) into lambda/,
# and `sam build` runs these targets from there with $(ARTIFACTS_DIR) set.

# Deps layer: install Linux x86_64 wheels regardless of the host platform
# (a Mac arm64 host would otherwise ship broken native wheels).
build-DepsLayer:
	uv pip install \
		-r requirements.txt \
		--python-platform x86_64-manylinux2014 \
		--python-version 3.12 \
		--only-binary :all: \
		--upgrade \
		--target "$(ARTIFACTS_DIR)/python"
	# Strip packages the Lambda runtime already provides
	rm -rf "$(ARTIFACTS_DIR)/python/boto3" \
	       "$(ARTIFACTS_DIR)/python/botocore" \
	       "$(ARTIFACTS_DIR)/python/s3transfer" \
	       "$(ARTIFACTS_DIR)/python/jmespath"
	# Trim metadata and vendored tests to shrink the layer
	# (email_validator needs its dist-info at import time)
	find "$(ARTIFACTS_DIR)/python" -maxdepth 1 -name "*.dist-info" \
		! -name "email_validator-*" -exec rm -rf {} +
	find "$(ARTIFACTS_DIR)/python" -type d -name tests -exec rm -rf {} + 2>/dev/null || true

# Function code: just the api package (deps come from the layer at /opt/python)
build-ApiFunction:
	cp -r api "$(ARTIFACTS_DIR)/api"

build-ProcessorFunction:
	cp -r api "$(ARTIFACTS_DIR)/api"
