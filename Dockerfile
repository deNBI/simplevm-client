FROM python:3.13.5
RUN echo "deb https://deb.debian.org/debian/ stable main" > /etc/apt/sources.list
RUN apt-get update -y \
    && apt-get install -y build-essential python3-openstackclient vim\
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
