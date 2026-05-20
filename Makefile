.PHONY: help ui travel-post test-railplanner lint-railplanner build-jekyll serve-jekyll clean

help:
	@echo "Usage:"
	@echo "  make travel-post    — Launch the Sprint Blog Generator UI + open browser"
	@echo "  make test-railplanner — Run Rail Planner Python tests"
	@echo "  make lint-railplanner — Lint-check all Rail Planner Python files"
	@echo "  make build-jekyll     — Build the Jekyll site"
	@echo "  make serve-jekyll     — Serve the Jekyll site locally"
	@echo "  make clean            — Clean tox and Jekyll caches"
	@echo ""
	@echo "See tox.ini and assets/py/Rail Planner/ for more detail."

# ---- Sprint Blog Generator UI ----

RAIL_DIR = "assets/py/Rail Planner"

ui: travel-post

travel-post:
	@echo "Starting Sprint Blog Generator UI at http://localhost:8080"
	@cd $(RAIL_DIR) && python3 -m ui.server &
	@sleep 2
	@python3 -c "import webbrowser; webbrowser.open('http://localhost:8080')"
	@wait

# ---- Rail Planner Python ----

test-railplanner:
	cd $(RAIL_DIR) && python3 -m pytest tests/ $(ARGS)

lint-railplanner:
	@cd $(RAIL_DIR) && python3 -c "import py_compile; [py_compile.compile(f, doraise=True) for f in 'time_util.py geo.py emissions.py rail_planner.py truth/snapshot.py curation/state.py narrative/blog.py generate_blog.py ui/server.py ui/post_parser.py'.split()]; print('All Rail Planner files compile OK')"

# ---- Tox ----

tox-test:
	tox run -e railplanner-test

tox-lint:
	tox run -e railplanner-lint

# ---- Jekyll ----

build-jekyll:
	bundle exec jekyll build --lsi

serve-jekyll:
	bundle exec jekyll serve --lsi

# ---- Cleanup ----

clean:
	rm -rf .tox/ _site/ .jekyll-cache/
	find assets/py/Rail Planner -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
