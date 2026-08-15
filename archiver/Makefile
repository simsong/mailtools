.PHONY: check run test-e2e

check: test-e2e

run:
	uv run mailarchiver $(ARGS)

test-e2e:
	uv run pytest -q tests/test_end_to_end.py
