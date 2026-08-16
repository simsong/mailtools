.PHONY: check run test

check: test

run:
	uv run mailarchiver $(ARGS)

test:
	uv run pytest -q
