#!/bin/bash


# Create a configuration file with the token
echo "METADATA_ACCESS_TOKEN='$METADATA_AUTH_TOKEN'" > /etc/metadata_config.env

# Secure the file permissions
chmod 600 /etc/metadata_config.env

# Source the configuration file for immediate use in the current session
source /etc/metadata_config.env

# Print a message to indicate completion
echo "Token has been set and configuration file created at /etc/metadata_config.env"
