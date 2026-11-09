FROM python:3.14.10-alpine3.24@sha256:a18b20ad69e74df6cf6d2e1b1a260d7a1ecf5380fd83b310f83ba88c461cf894

# Install SSH client and build dependencies needed for compiling Python packages
# We combine build-dep installation and removal with pip install in a single layer
# to avoid including build tools (like binutils) in the final image.
COPY requirements.txt /code/requirements.txt
RUN apk upgrade --no-cache && \
    apk add --no-cache openssh-client && \
    apk add --no-cache --virtual .build-deps \
        build-base \
        libffi-dev \
        openssl-dev \
        musl-dev \
        git && \
    pip install --no-cache-dir -r /code/requirements.txt openstackclient && \
    apk del .build-deps

# Copy requirements.yml and install Ansible roles
COPY requirements.yml /code/requirements.yml
COPY ansible.cfg /etc/ansible/
RUN ansible-galaxy install -r /code/requirements.yml

# Copy the entire project
COPY . /code

# Set PYTHONPATH to include the project root
ENV PYTHONPATH=/code

WORKDIR /code/simple_vm_client
