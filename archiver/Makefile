.PHONY: check run search test test-mailsearch test-headers install-mac install-linux install-tika

TIKA_VERSION ?= 3.3.2
TIKA_DIR ?= $(CURDIR)/.tools/tika/$(TIKA_VERSION)
TIKA_JAR := $(TIKA_DIR)/tika-app-$(TIKA_VERSION).jar
TIKA_SHA512 := $(TIKA_JAR).sha512
TIKA_URL := https://downloads.apache.org/tika/$(TIKA_VERSION)/tika-app-$(TIKA_VERSION).jar

check: test

run:
	uv run mailarchiver $(ARGS)

search:
	uv run mailsearch $(ARGS)

test:
	uv run pytest -q

test-mailsearch:
	uv run pytest -q tests/test_mailsearch.py

test-headers:
	uv run pytest -q tests/test_message.py tests/test_search.py

install-mac:
	@test "$$(uname -s)" = Darwin || { echo "install-mac must run on macOS"; exit 1; }
	@$(MAKE) install-tika

install-linux:
	@test "$$(uname -s)" = Linux || { echo "install-linux must run on Linux"; exit 1; }
	@$(MAKE) install-tika

install-tika:
	@command -v java >/dev/null || { echo "Apache Tika needs a Java runtime (Java 17 or newer)."; exit 1; }
	@mkdir -p "$(TIKA_DIR)"
	curl --fail --location --output "$(TIKA_JAR)" "$(TIKA_URL)"
	curl --fail --location --output "$(TIKA_SHA512)" "$(TIKA_URL).sha512"
	@expected=$$(awk '{print $$1}' "$(TIKA_SHA512)"); actual=$$(shasum -a 512 "$(TIKA_JAR)" | awk '{print $$1}'); test "$$expected" = "$$actual" || { echo "Tika SHA-512 verification failed"; rm -f "$(TIKA_JAR)" "$(TIKA_SHA512)"; exit 1; }
	@echo "Installed and verified $(TIKA_JAR)"
