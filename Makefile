PYTHON ?= $(shell [ -f .venv/bin/python ] && echo .venv/bin/python || command -v python3 2>/dev/null || echo python)


.PHONY: setup syntax test database process trade

setup:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

syntax:
	$(PYTHON) -B -c 'source = open("gemini_vision.py").read(); compile(source, "gemini_vision.py", "exec")'
	$(PYTHON) -B -c 'source = open("makeDatabase.py").read(); compile(source, "makeDatabase.py", "exec")'
	$(PYTHON) -B -c 'source = open("app.py").read(); compile(source, "app.py", "exec")'
	$(PYTHON) -B -c 'source = open("addNewSet.py").read(); compile(source, "addNewSet.py", "exec")'

test:
	$(PYTHON) -m unittest discover -s tests

database:
	$(PYTHON) makeDatabase.py

process:
	$(PYTHON) gemini_vision.py

trade:
	$(PYTHON) tradeEngine.py

run:
	$(PYTHON) -m streamlit run app.py


