# Payment-Integrity Claims Reviewer — task runner.
#
# Targets use whatever `python` is on PATH, so isolation is the caller's choice:
# create/activate a venv first (see README quickstart) and these targets use it.
# Override the interpreter with:  make run PY=.venv/Scripts/python
PY ?= python

.PHONY: install seed detect explain run eval holdout test reset fmt

install:        ## install dependencies into the active interpreter
	$(PY) -m pip install -r requirements.txt

seed:           ## generate synthetic claims + ground-truth labels into SQLite
	$(PY) -m app.seed

detect:         ## run the transparent rules engine; persist flags + triggers
	$(PY) -m app.detect

explain:        ## generate LLM rationales for flags (needs ANTHROPIC_API_KEY in .env)
	$(PY) -m app.explain

run:            ## start the FastAPI app at http://localhost:8000
	$(PY) -m uvicorn app.main:app --reload

eval:           ## detector P/R/F1 by issue type + explanation faithfulness (on the demo seed)
	$(PY) -m app.eval

holdout:        ## detector P/R/F1 on a SEPARATELY-written holdout set (the honest number)
	$(PY) -m app.holdout

test:           ## run the test suite
	$(PY) -m pytest

reset:          ## wipe DB, re-seed, re-detect — clean, repeatable demo state
	$(PY) -c "import os,glob;[os.remove(f) for f in glob.glob('data/*.db')]"
	$(PY) -m app.seed
	$(PY) -m app.detect

fmt:            ## format code
	$(PY) -m black app
