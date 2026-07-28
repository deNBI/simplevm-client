# Requirements for new cloud sites

## Overview

This document describes the technical requirements a new site must meet in order to be connected to a central SimpleVM installation.

## OpenStack Projects

- Two separate OpenStack projects must be provisioned at the site:
  - **Staging** – for testing and validation
  - **Production** – for live workloads
- Each project should have its own quotas, credentials, and network isolation as appropriate.
- Staging and production each get their own external address and domain name. Nothing is shared between the two environments.

## Network / Connectivity

### Externally Reachable Address

- The site requires a publicly (externally) reachable IP address.
- For full functionality, both the IP address and a FQDN must be available (not one or the other).

### Domain Name

- A domain name must be provided and mapped to the IP address of the application.
- The domain name is used for external access and should match the certificate used for HTTPS (port 443).
- DNS records are provided either by the cloud site or by the developer team, depending on the specific deployment.
- The domain name must be a Fully Qualified Domain Name (FQDN). Subdomains are permitted and commonly used to distinguish environments, e.g.:
  - `app.staging.example.com` → staging
  - `app.example.com` → production

### Required Ports

| Port / Range              | Purpose                              | Notes                                          |
|----------------------------|----------------------------------------|-------------------------------------------------|
| 30000 – 30256              | SSH gateway access for users           | Range can be extended if needed                 |
| 80 / 443                   | HTTP / HTTPS – Web Gateway forwarding   | Forwarding required                             |
| Client port (e.g. 9000)    | Communication with the central application | Port is freely selectable, usually 9000 for us  |

> **Note:** The port range 30000–30256 is a starting value and can be extended as needed (e.g. if more nodes/services are added).

### Firewall Rules

- The client port is not publicly exposed. Access must be restricted so that only the central web application can reach it (source IP restriction to the central web application).

### TLS Certificates

- TLS certificates are issued via Let's Encrypt.
