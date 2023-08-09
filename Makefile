DOCS_DIR := ./docs

PROJECT := pact-python
PYTHON_MAJOR_VERSION := 3.9

sgr0 := $(shell tput sgr0)
red := $(shell tput setaf 1)
green := $(shell tput setaf 2)

help:
	@echo ""
	@echo "  clean      to clear build and distribution directories"
	@echo "  deps       to install the required files for development"
	@echo "  examples   to run the example end to end tests (consumer, fastapi, flask, messaging)"
	@echo "  consumer   to run the example consumer tests"
	@echo "  fastapi    to run the example FastApi provider tests"
	@echo "  flask      to run the example Flask provider tests"
	@echo "  messaging  to run the example messaging e2e tests"
	@echo "  grpc       to run the example grpc e2e tests"
	@echo "  todo		to run the example todo tests"
	@echo "  examples_v3   to run the example end to end tests (consumer_v3, fastapi_v3, flask_v3, messaging_v3)"
	@echo "  consumer_v3   to run the example consumer V3 tests"
	@echo "  fastapi_v3    to run the example FastApi V3  provider tests"
	@echo "  flask_v3      to run the example Flask V3  provider tests"
	@echo "  messaging_v3  to run the example messaging V3 e2e tests"
	@echo "  examples_v4   to run the example end to end tests (grpc_v4)"
	@echo "  grpc_v4       to run the example grpc V4 e2e tests"
	@echo "  todo		to run the example todo tests"
	@echo "  package    to create a distribution package in /dist/"
	@echo "  release    to perform a release build, including deps, test, and package targets"
	@echo "  test       to run all tests"
	@echo "  venv       to setup a venv under .venv using pyenv, if available"
	@echo ""


.PHONY: release
release: deps test package


.PHONY: clean
clean:
	rm -rf build
	rm -rf dist
	rm -rf pact/bin


.PHONY: deps
deps:
	pip install -r requirements_dev.txt -e .


define CONSUMER
	echo "consumer make"
	cd examples/consumer
	pip install -q -r requirements.txt
	pip install -e ../../
	./run_pytest.sh
endef
export CONSUMER


define FLASK_PROVIDER
	echo "flask make"
	cd examples/flask_provider
	pip install -q -r requirements.txt
	pip install -e ../../
	./run_pytest.sh
endef
export FLASK_PROVIDER


define FASTAPI_PROVIDER
	echo "fastapi make"
	cd examples/fastapi_provider
	pip install -q -r requirements.txt
	pip install -e ../../
	./run_pytest.sh
endef
export FASTAPI_PROVIDER


define MESSAGING
	echo "messaging make"
	cd examples/message
	pip install -q -r requirements.txt
	pip install -e ../../
	./run_pytest.sh
endef
export MESSAGING

define CONSUMER_V3
	echo "consumer make"
	cd examples/v3/consumer
	pip install -q -r requirements.txt
	pip install -e ../../../
	./run_pytest.sh
endef
export CONSUMER_V3


define FLASK_PROVIDER_V3
	echo "flask make"
	cd examples/v3/flask_provider
	pip install -q -r requirements.txt
	pip install -e ../../../
	./run_pytest.sh
endef
export FLASK_PROVIDER_V3


define FASTAPI_PROVIDER_V3
	echo "fastapi make"
	cd examples/v3/fastapi_provider
	pip install -q -r requirements.txt
	pip install -e ../../../
	./run_pytest.sh
endef
export FASTAPI_PROVIDER_V3


define MESSAGING_V3
	echo "messaging make"
	cd examples/v3/message
	pip install -q -r requirements.txt
	pip install -e ../../../
	./run_pytest.sh
endef
export MESSAGING_V3


define TODO_V3
	echo "todo make"
	cd examples/v3/todo
	pip install -r requirements.txt
	pip install -e ../../../
	./run_pytest.sh
endef
export TODO_V3

define GRPC_V4
	echo "grpc make"
	cd examples/v4/grpc
	pip install -q -r requirements.txt
	pip install -e ../../../
	./run_pytest.sh
endef
export GRPC_V4

.PHONY: consumer
consumer:
	bash -c "$$CONSUMER"


.PHONY: flask
flask:
	bash -c "$$FLASK_PROVIDER"


.PHONY: fastapi
fastapi:
	bash -c "$$FASTAPI_PROVIDER"


.PHONY: messaging
messaging:
	bash -c "$$MESSAGING"


.PHONY: consumer_v3
consumer_v3:
	bash -c "$$CONSUMER_V3"


.PHONY: flask_v3
flask_v3:
	bash -c "$$FLASK_PROVIDER_V3"


.PHONY: fastapi_v3
fastapi_v3:
	bash -c "$$FASTAPI_PROVIDER_V3"


.PHONY: messaging_v3
messaging_v3:
	bash -c "$$MESSAGING_V3"

.PHONY: todo_v3
todo_v3:
	bash -c "$$TODO_V3"

.PHONY: grpc
grpc_v4:
	bash -c "$$GRPC_V4"



.PHONY: examples
examples: consumer flask fastapi messaging
examples_v3: consumer_v3 flask_v3 fastapi_v3 messaging_v3 todo_v3
examples_v4: grpc_v4
# examples: consumer flask fastapi messaging todo


.PHONY: package
package:
	python setup.py sdist


.PHONY: test
test: deps
	flake8 --exclude '*pb2*',.git,__pycache__,build,dist,.tox --show-source
	pydocstyle pact
	coverage erase
	tox
	coverage report -m --fail-under=100

.PHONY: venv
venv:
	@if [ -d "./.venv" ]; then echo "$(red).venv already exists, not continuing!$(sgr0)"; exit 1; fi
	@type pyenv >/dev/null 2>&1 || (echo "$(red)pyenv not found$(sgr0)"; exit 1)

	@echo "\n$(green)Try to find the most recent minor version of the major version specified$(sgr0)"
	$(eval PYENV_VERSION=$(shell pyenv install -l | grep "\s\s$(PYTHON_MAJOR_VERSION)\.*" | tail -1 | xargs))
	@echo "$(PYTHON_MAJOR_VERSION) -> $(PYENV_VERSION)"

	@echo "\n$(green)Install the Python pyenv version if not already available$(sgr0)"
	pyenv install $(PYENV_VERSION) -s

	@echo "\n$(green)Make a .venv dir$(sgr0)"
	~/.pyenv/versions/${PYENV_VERSION}/bin/python3 -m venv ${CURDIR}/.venv

	@echo "\n$(green)Make it 'available' to pyenv$(sgr0)"
	ln -sf ${CURDIR}/.venv ~/.pyenv/versions/${PROJECT}

	@echo "\n$(green)Use it! (populate .python-version)$(sgr0)"
	pyenv local ${PROJECT}
