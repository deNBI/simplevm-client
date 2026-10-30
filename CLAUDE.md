# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

### Development & Setup
- **Linting:** `make lint` (runs `flake8`)
- **Documentation:** `make docs` (generates documentation in `/docs`)
- **Thrift Code Gen:** `make thrift_py` (generates Python code from `portal_client.thrift`)
- **Local Dev (Docker):** `make dev` or `docker-compose -f docker-compose.dev.yml up --build`
- **Local Dev with Bibigrid:** `make dev-bibigrid`

### Testing
- **Run Tests:** `pytest` (configured via `pytest.ini`)
- **Single Test:** `pytest path/to/test_file.py::test_function_name`

## High-Level Architecture

### Project Structure
```text
simple_vm_client/
├── bibigrid_connector/         # Cluster management via Bibigrid
│   └── bibigrid_connector.py
├── config/                     # Configuration YAML files
│   └── config.yml
├── forc_connector/             # Research environment & playbook management
│   ├── forc_connector.py
│   ├── playbook/               # Playbook execution logic
│   │   └── playbook.py
│   └── template/               # RE templates and logic
│       └── template.py
├── flavor_resource_exporter_connector/ # External flavor resource fetching
│   └── flavor_resource_exporter_connector.py
├── metadata_connector/         # VM metadata server integration
│   └── metadata_connector.py
├── openstack_connector/        # Primary OpenStack SDK wrapper
│   └── openstack_connector.py
├── util/                       # Shared utilities
│   ├── logger.py
│   ├── state_enums.py
│   └── thrift_converter.py     # OpenStack SDK -> Thrift object conversion
├── VirtualMachineHandler.py    # Main business logic orchestrator
├── VirtualMachineServer.py     # Thrift RPC server implementation
├── VirtualMachineService.py    # Thrift service definition (generated)
├── ttypes.py                   # Thrift type definitions (generated)
└── constants.py                # Project-wide constants
```

SimpleVM Client is a Python-based integration layer that manages cloud infrastructure, primarily OpenStack, via a Thrift RPC interface.


### Core Components
- **Thrift Interface (`portal_client.thrift`):** Defines the service contract (`VirtualMachineService`), data structures (`VM`, `Flavor`, `Image`), and exceptions used for communication with the Django backend.
- **Service Layer (`simple_vm_client/VirtualMachineServer.py` & `VirtualMachineHandler.py`):**
    - `VirtualMachineServer.py`: Implements the Thrift server logic.
    - `VirtualMachineHandler.py`: The central orchestrator. It implements the Thrift `Iface` and delegates actual operations to specialized connectors.
- **Connectors (`simple_vm_client/*/`):**
    - `openstack_connector/`: Primary interface for OpenStack operations (VM lifecycle, volumes, networks).
    - `forc_connector/`: Manages research environment backends and playbook deployments.
    - `bibigrid_connector/`: Handles cluster management via Bibigrid.
    - `metadata_connector/`: Manages metadata server data for VMs.
    - `flavor_resource_exporter_connector/`: Fetches flavor resources from an external exporter.
- **Utilities (`simple_vm_client/util/`):**
    - `thrift_converter.py`: Essential utility for converting OpenStack SDK objects to Thrift-compatible Python objects.

### Key Integration Patterns
1. **Backend $\rightarrow$ Client:** The Django backend calls the Client via Thrift RPC.
2. **Client $\rightarrow$ Cloud:** The `VirtualMachineHandler` uses the `OpenStackConnector` (wrapping `openstacksdk`) to execute actions on the cloud.
3. **Resource Flow:**
   - Thrift Request $\rightarrow$ `VirtualMachineServer` $\rightarrow$ `VirtualMachineHandler` $\rightarrow$ `Connector` $\rightarrow$ Cloud API.
   - Cloud Response $\rightarrow$ `Connector` $\rightarrow$ `thrift_converter` $\rightarrow$ Thrift Response.

### Important Files
- `portal_client.thrift`: The source of truth for the public API.
- `simple_vm_client/VirtualMachineHandler.py`: The main entry point for business logic.
- `simple_vm_client/config/config.yml`: Base configuration.
