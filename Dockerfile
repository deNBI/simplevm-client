FROM python:3.11.4-buster

RUN apt-get update -y \
    && apt-get install -y build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

# Copy requirements and install them first to leverage Docker cache
COPY requirements.txt /code
RUN pip install -r requirements.txt

COPY requirements.yml /code
COPY ansible.cfg /etc/ansible/
RUN ansible-galaxy install -r requirements.yml

# Copy the entire project
COPY . /code

# Set PYTHONPATH to include the project root
ENV PYTHONPATH /code

WORKDIR /code/simple_vm_client
