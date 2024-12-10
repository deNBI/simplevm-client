#!/bin/bash
declare -a keys_to_add=KEYS_TO_ADD
USER_TO_SET="${USER_TO_SET:-ubuntu}"
USER_HOME="/home/${USER_TO_SET}"
METADATA_AUTHORIZED_KEYS_FILE="${USER_HOME}/.ssh/metadata_authorized_keys"
SSHD_CONFIG_FILE="/etc/ssh/sshd_config"
AUTHORIZED_KEYS_LINE="AuthorizedKeysFile .ssh/authorized_keys /home/%u/.ssh/authorized_keys /home/%u/.ssh/metadata_authorized_keys"
# Validate if KEYS_TO_ADD is set properly to avoid empty file operations
if [ ${#keys_to_add[@]} -eq 0 ]; then
    echo "No keys provided in KEYS_TO_ADD."
    exit 1
fi

# Create the authorized keys file and add the keys
touch "$METADATA_AUTHORIZED_KEYS_FILE"
echo "Adding ${#keys_to_add[@]} keys to $METADATA_AUTHORIZED_KEYS_FILE"
for key in "${keys_to_add[@]}"; do
    printf "\n%s" "$key" >> "$METADATA_AUTHORIZED_KEYS_FILE"
done

# Set correct permissions for the metadata_authorized_keys file
chown "$USER_TO_SET:$USER_TO_SET" "$METADATA_AUTHORIZED_KEYS_FILE"


# Check if the line is already in the configuration file and update or append accordingly
if grep -qE '^#?[[:space:]]*AuthorizedKeysFile' "$SSHD_CONFIG_FILE"; then
    echo "MATCHED: An existing AuthorizedKeysFile line was found. Updating..."
    sed -i.bak -E "s|^#?[[:space:]]*AuthorizedKeysFile.*|$AUTHORIZED_KEYS_LINE|" "$SSHD_CONFIG_FILE"
else
    echo "NOT MATCHED: No existing AuthorizedKeysFile line found. Adding the line."
    echo "$AUTHORIZED_KEYS_LINE" >> "$SSHD_CONFIG_FILE"
fi

echo "Reloading and restarting SSH service..."
systemctl daemon-reload
service sshd restart
