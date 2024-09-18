#!/bin/bash

# Use clear placeholders that will be replaced in the Python script
TOKEN_ESCAPED='REPLACE_WITH_ACTUAL_TOKEN'
METADATA_INFO_ENDPOINT_ESCAPED='REPLACE_WITH_ACTUAL_METADATA_INFO_ENDPOINT'

# Create a configuration file with the token in /etc/simplevm directory
CONFIG_DIR="/etc/simplevm"
CONFIG_FILE_PATH="$CONFIG_DIR/metadata_config.env"

# Check if the config directory already exists
if [ -d "$CONFIG_DIR" ]; then
  echo "Config directory $CONFIG_DIR already exists."
else
  # Create the config directory with permissions that allow only root to read and write it
  mkdir -p "$CONFIG_DIR" || { echo "Error creating directory $CONFIG_DIR"; exit 1; }
  chmod 700 "$CONFIG_DIR"
  chown root:root "$CONFIG_DIR"
fi

# Validate token value
if [ -z "${TOKEN_ESCAPED}" ]; then
    echo "Error: Token cannot be empty"
    exit 1
fi

# Create the config file with permissions that allow only root to read it
echo "METADATA_ACCESS_TOKEN=$TOKEN_ESCAPED" > "$CONFIG_FILE_PATH" || { echo "Error writing to file $CONFIG_FILE_PATH"; exit 1; }
chmod 600 "$CONFIG_FILE_PATH"
chown root:root "$CONFIG_FILE_PATH"

# Validate metadata info endpoint value
if [ -z "${METADATA_INFO_ENDPOINT_ESCAPED}" ]; then
    echo "Error: Metadata info endpoint cannot be empty"
    exit 1
fi

echo "METADATA_INFO_ENDPOINT=$METADATA_INFO_ENDPOINT_ESCAPED" >> "$CONFIG_FILE_PATH" || { echo "Error writing to file $CONFIG_FILE_PATH"; exit 1; }

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    echo "jq is not installed. Installing..."
    sudo apt-get update && sudo apt-get install -y jq || { echo "Error installing jq"; exit 1; }
fi

# Create the /etc/simplevm/get_metadata.sh script to fetch metadata using the saved token
SCRIPT_DIR="$CONFIG_DIR"
SCRIPT_NAME="get_metadata.sh"
SCRIPT_PATH="$SCRIPT_DIR/$SCRIPT_NAME"

cat <<'EOF' > "$SCRIPT_PATH"
#!/bin/bash
source /etc/simplevm/metadata_config.env

# Construct the URL with hostname query param
INFO_ENDPOINT_URL="${METADATA_INFO_ENDPOINT}?hostname=$(hostname)"

# Define the auth header with the token
AUTH_HEADER="auth_token: ${METADATA_ACCESS_TOKEN}"

# Get real metadata endpoint from config if available
REAL_METADATA_ENDPOINT=$(grep '^REAL_METADATA_ENDPOINT=' "/etc/simplevm/metadata_config.env" | cut -d '=' -f 2-)

if [ -z "${REAL_METADATA_ENDPOINT}" ]; then
    # Fetch the JSON response from the info endpoint to get real metadata endpoint
    info_response=$(curl -s -X GET "${INFO_ENDPOINT_URL}" -H "${AUTH_HEADER}")

    if [ $? -ne 0 ]; then
        echo "Error: Failed to fetch metadata endpoint"
        exit 1
    fi

    # Validate the JSON response
    if ! jq -e '.metadata_endpoint' <<< "${info_response}" &> /dev/null; then
        echo "Error: Invalid JSON response from metadata endpoint"
        exit 1
    fi

    # Extract the actual metadata endpoint from the response
    REAL_METADATA_ENDPOINT=$(jq -r '.metadata_endpoint' <<< "${info_response}")

    # Save real metadata endpoint to config
    echo "REAL_METADATA_ENDPOINT=${REAL_METADATA_ENDPOINT}" >> "/etc/simplevm/metadata_config.env"
fi

# Fetch the actual metadata from the extracted endpoint
LOCAL_IP=$(hostname -I | awk '{print $1}')
metadata_response=$(curl -s -X GET "${REAL_METADATA_ENDPOINT}/metadata/${LOCAL_IP}" -H "${AUTH_HEADER}")

if [ $? -ne 0 ]; then
    echo "Error: Failed to fetch metadata"
    exit 1
fi

echo "${metadata_response}"
EOF

# Make the script executable and owned by root
chmod 700 "$SCRIPT_PATH"
chown root:root "$SCRIPT_PATH"

# Print a message to indicate completion
echo "Token has been set, configuration file created at $CONFIG_FILE_PATH with restricted access."
echo "/etc/simplevm/get_metadata.sh script created to fetch metadata using the saved token."
