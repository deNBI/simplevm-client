FROM python:3.14.10-alpine3.24@sha256:eb2c62658b8d51bff0acc408504b76521d02030de56a8a3c1e830083e89b89d2

# Install SSH client and build dependencies needed for compiling Python packages
RUN apk upgrade --no-cache && \
    apk add --no-cache \
        openssh-client \
        && apk add --no-cache --virtual .build-deps \
        build-base \
        libffi-dev \
        openssl-dev \
        musl-dev \
        git

# Copy requirements and install them first to leverage Docker cache
COPY requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir -r /code/requirements.txt openstackclient

# Copy requirements.yml and install Ansible roles
COPY requirements.yml /code/requirements.yml
COPY ansible.cfg /etc/ansible/
RUN ansible-galaxy install -r /code/requirements.yml

# Copy the entire project
COPY . /code

# Set PYTHONPATH to include the project root
ENV PYTHONPATH=/code

WORKDIR /code/simple_vm_client
