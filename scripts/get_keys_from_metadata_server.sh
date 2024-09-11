#!/bin/bash

# Load the auth token from .metadata_config.env
source ~/.metadata_config.env

# Define the URL and machine IP
URL="http://192.168.2.122:8000/metadata/192.168.2.74"
AUTH_HEADER="auth_token: ${METADATA_ACCESS_TOKEN}"

# Fetch the JSON response from the URL
response=$(curl -s -X GET "$URL" -H "$AUTH_HEADER")

# Extract the public_keys array from the JSON response
public_keys=$(echo "$response" | jq -r '.public_keys[]')

# Check if public_keys is empty
if [ -z "$public_keys" ]; then
  echo "No public keys found. authorized_keys file not updated."
  exit 0
fi

# Ensure the .ssh directory and authorized_keys file exist
mkdir -p ~/.ssh
touch ~/.ssh/authorized_keys

# Function to check if a key already exists in the authorized_keys file
key_exists() {
  grep -Fqx "$1" ~/.ssh/authorized_keys
}

# Add keys to authorized_keys if they don't already exist
added_keys=0

while IFS= read -r key; do
  if ! key_exists "$key"; then
    echo "$key" >> ~/.ssh/authorized_keys
    ((added_keys++))
  fi
done <<< "$public_keys"

if [ $added_keys -gt 0 ]; then
  echo "$added_keys new public key(s) have been added to the authorized_keys file."
else
  echo "All public keys were already present. No changes made to authorized_keys file."
fi