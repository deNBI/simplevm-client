# SimpleVM Client

Python 3.14 Thrift server that `simplevm-backend` (Django) talks to — one instance per OpenStack cluster. Manages VMs, volumes, snapshots, clusters, bibigrid, FORC research environments, a metadata server and a flavor resource exporter. The API is defined in `portal_client.thrift`.

## Commands

`make help` lists targets. Dev flow is Docker Compose; it needs `.env` (copy `.env.in`, fill `OS_*` OpenStack credentials, `FORC_API_KEY`, `METADATA_WRITE_TOKEN`) and `simple_vm_client/keys/localhost/server.pem` (gitignored — create per README "Create certificates"; the dev compose mounts it into the container).

```bash
make dev              # client + redis + metadata server (docker-compose.dev.yml)
make dev-bibigrid     # dev stack + bibigrid
make multicloud       # multiple clusters side by side (docker-compose.dev.multicloud.yml)
make dev-down         # tear down
make production       # production stack from image tag CLOUD_PORTAL_CLIENT_TAG in .env
```

- Container name is `simplevm-client` in both dev and production compose files: `docker logs simplevm-client`, `docker exec -it simplevm-client bash`.
- Dev container mounts `simple_vm_client/config/config_local.yml` as `/code/simple_vm_client/config.yml` — edit `config_local.yml`, not `config.yml` (that is the template). `config_local_bielefeld.yml`/`config_local_giessen.yml` are per-site variants.
- Internal Thrift port is 9090; `CLIENT_PORT` in `.env` is the host-side mapping.

### Tests

Unit tests only (unittest + mocks/`openstack.test` fakes, no live OpenStack needed). CI (`.github/workflows/coverage.yml`) runs plain `pytest` on Python 3.14 after `pip install -r requirements.txt` — same works locally:

```bash
pytest
pytest simple_vm_client/tests/test_virtualmachinehandler.py::TestVirtualMachineHandler::test_get_images
make run-pytest   # alternative: runs pytest inside Dockerfile-tests (coverage)
```

### Lint

`pre-commit run --all-files` — black, isort, flake8 (setup.cfg, max line 140), autoflake, pep585-upgrade (modern PEP 585/604 type hints), pip-audit; gitleaks runs post-commit.
Do NOT use `make lint` — it is broken (points at the removed `VirtualMachineService/` directory).

### Thrift codegen

`make thrift_py` (requires the thrift compiler) regenerates `simple_vm_client/{VirtualMachineService.py,ttypes.py,constants.py}` from `portal_client.thrift`. Generated files are excluded from lint/coverage — never hand-edit them.
After changing the `.thrift` file, `simplevm-backend` needs the regenerated files too — but over there the imports must be relative (`from .ttypes import *`), so copy and adjust.

## File map

- `portal_client.thrift` — protocol definition, single source of truth for the API
- `simple_vm_client/VirtualMachineServer.py` — entrypoint: click CLI, Thrift TThreadPoolServer (optional TLS), loads the config yml
- `simple_vm_client/VirtualMachineHandler.py` — implements the Thrift `Iface`, delegates to connectors
- `simple_vm_client/openstack_connector/` — core logic (~3k lines): servers, volumes, snapshots, clusters
- `simple_vm_client/{bibigrid,forc,metadata,flavor_resource_exporter}_connector/` — optional subsystems, each toggled via `activated:` in config
- `simple_vm_client/util/` — logger, `thrift_converter` (openstack SDK objects → Thrift types), state enums
- `simple_vm_client/config/` — `config.yml` (template, committed) + `config_local*.yml`
- `simple_vm_client/{VirtualMachineService.py,ttypes.py,constants.py}` — Thrift-generated, do not edit
- `simple_vm_client/tests/`, `simple_vm_client/benchmark/` — pytest suite; load-test script via `make run_benchmark`
- `docker-compose.dev*.yml` — dev stacks; `docker-compose*.yml` (no `dev`) — production (prebuilt image + filebeat log shipping)
- `site.yml` + `plays/` — Ansible deployment to cluster hosts (`requirements.yml` = galaxy roles); `--extra-vars`: `repo_version`, `env_file`, `client_config`, `client_server_pem`
- `scripts/gateway/` — single-floating-IP gateway setup (iptables TCP/UDP, see `ProjectGateway.md`)
- `thrift-0.22.0/` — vendored Thrift compiler source (gitignored), not part of the app

## Gotchas

- README and Makefile still reference the old package dir `VirtualMachineService/`; the real package is `simple_vm_client/` (Dockerfile sets `PYTHONPATH=/code`, `WORKDIR=/code/simple_vm_client`). `make lint`, `make check_*`, `make client_logs` and `make enter_client_container` are all stale — use the commands above instead.
- `thrift-0.22.0/` is a full vendored compiler checkout — never lint, build, or commit it.
- Ansible deployment requires SSH agent forwarding on the target host (GitHub clone via forwarded key, README "Deployment via ansible").
- CI: PRs trigger image build + grype scan and a pytest coverage comment. PRs to `master` must come from a branch containing `staging` or `hotfix` (master-protection workflow); `dev` is the integration branch, releases are tagged (tag push builds the OCI image).
