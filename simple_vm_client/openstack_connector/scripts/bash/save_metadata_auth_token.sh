#!/bin/bash

# Use a clear placeholder that will be replaced in the Python script
TOKEN_ESCAPED='REPLACE_WITH_ACTUAL_TOKEN'

# Create a configuration file with the token
echo "METADATA_ACCESS_TOKEN='$TOKEN_ESCAPED'" > /etc/metadata_config.env

# Secure the file permissions
chmod 600 /etc/metadata_config.env

# Source the configuration file for immediate use in the current session
source /etc/metadata_config.env

# Print a message to indicate completion
echo "Token has been set and configuration file created at /etc/metadata_config.env"
