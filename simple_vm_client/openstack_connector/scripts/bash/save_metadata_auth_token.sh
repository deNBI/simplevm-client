#!/bin/bash

# Use a clear placeholder that will be replaced in the Python script
TOKEN_ESCAPED='REPLACE_WITH_ACTUAL_TOKEN'

# Create a configuration file with the token in the ubuntu user's home directory
UBUNTU_HOME_DIR="/home/ubuntu"
CONFIG_FILE_PATH="$UBUNTU_HOME_DIR/.metadata_config.env"

echo "METADATA_ACCESS_TOKEN='$TOKEN_ESCAPED'" > "$CONFIG_FILE_PATH"

# Secure the file permissions so only the ubuntu user can read it
chmod 600 "$CONFIG_FILE_PATH"
chown ubuntu:ubuntu "$CONFIG_FILE_PATH"

# Print a message to indicate completion
echo "Token has been set and configuration file created at $CONFIG_FILE_PATH with restricted access."
