#!/bin/bash

# Use clear placeholders that will be replaced in the Python script
TOKEN_ESCAPED='REPLACE_WITH_ACTUAL_TOKEN'
ENDPOINT_ESCAPED='REPLACE_WITH_ACTUAL_ENDPOINT'

# Create a configuration file with the token in the ubuntu user's home directory
UBUNTU_HOME_DIR="/home/ubuntu"
CONFIG_FILE_PATH="$UBUNTU_HOME_DIR/.metadata_config.env"

echo "METADATA_ACCESS_TOKEN='$TOKEN_ESCAPED'" > "$CONFIG_FILE_PATH"
echo "METADATA_SERVER_ENDPOINT='$ENDPOINT_ESCAPED'" >> "$CONFIG_FILE_PATH"

# Secure the file permissions so only the ubuntu user can read it
chmod 600 "$CONFIG_FILE_PATH"
chown ubuntu:ubuntu "$CONFIG_FILE_PATH"

# Create the ~/.get_metadata.sh script to fetch metadata using the saved token
SCRIPT_DIR="$UBUNTU_HOME_DIR"
SCRIPT_NAME=".get_metadata.sh"
SCRIPT_PATH="$SCRIPT_DIR/$SCRIPT_NAME"

echo "#!/bin/bash" > "$SCRIPT_PATH"
echo "source ~/.metadata_config.env" >> "$SCRIPT_PATH"
echo "" >> "$SCRIPT_PATH"
echo "# Define the metadata server endpoint and local machine IP" >> "$SCRIPT_PATH"
echo "SERVER_ENDPOINT=\\"$METADATA_SERVER_ENDPOINT\\"" >> "$SCRIPT_PATH"
echo "LOCAL_IP=\\$(ip route get 8.8.8.8 | awk '{print \\$7}' | tr -d '\\n')" >> "$SCRIPT_PATH"
echo "" >> "$SCRIPT_PATH"
echo "# Construct the URL" >> "$SCRIPT_PATH"
echo "URL=\\"\\${SERVER_ENDPOINT}/\\${LOCAL_IP}\\"" >> "$SCRIPT_PATH"
echo "" >> "$SCRIPT_PATH"
echo "# Define the auth header with the token" >> "$SCRIPT_PATH"
echo "AUTH_HEADER=\\"auth_token: \\${METADATA_ACCESS_TOKEN}\\"" >> "$SCRIPT_PATH"
echo "" >> "$SCRIPT_PATH"
echo "# Fetch the JSON response from the URL" >> "$SCRIPT_PATH"
echo "response=\\$(curl -s -X GET \\"\\$URL\\" -H \\"\\$AUTH_HEADER\\")" >> "$SCRIPT_PATH"
echo "" >> "$SCRIPT_PATH"
echo "echo \\"Response:\\"" >> "$SCRIPT_PATH"
echo "echo \\"\\$response\\"" >> "$SCRIPT_PATH"

# Make the script executable
chmod 700 "$SCRIPT_PATH"
chown ubuntu:ubuntu "$SCRIPT_PATH"

# Print a message to indicate completion
echo "Token has been set, configuration file created at $CONFIG_FILE_PATH with restricted access."
echo "~/.get_metadata.sh script created to fetch metadata using the saved token."
