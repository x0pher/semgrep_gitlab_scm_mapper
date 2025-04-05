import requests
import json
import os
import time
from datetime import datetime
import keyring

# Configuration
GITLAB_API_URL = "https://gitlab.your_domain.com/api/v4/groups"
GITLAB_ACCESS_TOKEN = keyring.get_password('gitlab', 'GITLAB_ACCESS_TOKEN')
SEMGREP_API_URL = "https://semgrep.dev/api/scm/deployments/deployment_id/configs"
SEMGREP_ACCESS_TOKEN = keyring.get_password('semgrep_api', 'SEMGREP_ACCESS_TOKEN')
LOG_FILE = "semgrep_api_calls.log"

# Proxy configuration
proxies = {
    "http": "http://proxy.your_domain.com:PORT",
    "https": "http://proxy.your_domain.com:PORT",
}

# File paths
log_file_path = os.path.join(os.getcwd(), LOG_FILE)

def get_gitlab_groups(page=1, per_page=100):
    headers = {"Private-Token": GITLAB_ACCESS_TOKEN}
    params = {"page": page, "per_page": per_page}
    response = requests.get(GITLAB_API_URL, headers=headers, params=params, proxies=proxies)
    print(f"GitLab API Response: {response.status_code}")
    if response.status_code == 200:
        try:
            groups = response.json()
            return groups
        except json.JSONDecodeError as e:
            log_message(f"Error decoding JSON response: {e}")
            print(f"Error decoding JSON response: {e}")
            return []
    else:
        log_message(f"Error fetching GitLab groups: {response.status_code}")
        return []

def get_semgrep_configs():
    headers = {"Authorization": f"Bearer {SEMGREP_ACCESS_TOKEN}"}
    response = requests.get(SEMGREP_API_URL, headers=headers, proxies=proxies)
    print(f"Semgrep GET Configs API Response: {response.status_code}")
    if response.status_code == 200:
        try:
            configs = response.json()["configs"]
            print(f"Fetched {len(configs)} configs from Semgrep")
            return configs
        except json.JSONDecodeError as e:
            log_message(f"Error decoding JSON response: {e}")
            print(f"Error decoding JSON response: {e}")
            return []
    else:
        log_message(f"Error fetching Semgrep configs: {response.status_code}")
        return []

def log_message(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file_path, "a") as f:
        f.write(f"{timestamp} - {message}\n")

def log_response(response, action):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file_path, "a") as f:
        if response.status_code == 200:
            if response.text == "{}":
                f.write(f"{timestamp} - {action} successful: {response.status_code} OK\n")
            else:
                f.write(f"{timestamp} - {action} successful: {response.status_code} OK\n{response.text}\n")
        elif response.status_code == 404:
            f.write(f"{timestamp} - {action} error: {response.status_code} - Not Found\n")
        elif response.status_code == 409:
            f.write(f"{timestamp} - {action} SCM already exists, no action taken: {response.status_code}\n{response.text}\n")
        else:
            f.write(f"{timestamp} - {action} error: {response.status_code}\n")

def call_semgrep_api(item, method):
    if method == "POST":
        payload = {
            "type": "SCM_TYPE_GITLAB_SELFMANAGED",
            "baseUrl": "https://gitlab.your_domain.com",
            "namespace": item["full_path"],
            "accessToken": GITLAB_ACCESS_TOKEN
        }
        headers = {"Authorization": f"Bearer {SEMGREP_ACCESS_TOKEN}"}
        response = requests.post(SEMGREP_API_URL, json=payload, headers=headers, proxies=proxies)
        log_response(response, method)
    elif method == "DELETE":
        config_id = item["id"]
        delete_url = SEMGREP_API_URL + "/" + str(config_id)
        headers = {"Authorization": f"Bearer {SEMGREP_ACCESS_TOKEN}"}
        response = requests.delete(delete_url, headers=headers, proxies=proxies)
        log_response(response, method)
    time.sleep(1)  # Rate limiting: wait for 1 second between API calls

def main():
    log_message("Script started")
    
    log_message("Fetching current GitLab groups")
    current_groups = []
    page = 1
    while True:
        groups = get_gitlab_groups(page=page)
        if not groups:
            break
        current_groups.extend(groups)
        page += 1
    
    print(f"Total groups fetched: {len(current_groups)}")

    log_message("Fetching current Semgrep configs")
    semgrep_configs = get_semgrep_configs()
    
    current_group_names = {group["full_path"] for group in current_groups}
    semgrep_config_names = {config["namespace"] for config in semgrep_configs}

    new_groups = current_group_names - semgrep_config_names
    removed_configs = semgrep_config_names - current_group_names

    parsed_removed_configs = []
    for config in semgrep_configs:
        if config["namespace"] in removed_configs and 'gitlab' in config['baseUrl']:
            parsed_removed_configs.append(config)

    parsed_removed_configs = {config["namespace"] for config in parsed_removed_configs}

    if len(new_groups) > 0:
        log_message(f"Adding to Semgrep: {new_groups}")
    else:
        log_message("No SCMs to add")

    for group in current_groups:
        if group["full_path"] in new_groups:
            call_semgrep_api(group, "POST")

    log_message("Fetching old configs from Semgrep")
    if len(parsed_removed_configs) > 0:
        log_message(f"Configs to remove from Semgrep: {parsed_removed_configs}")
    else:
        log_message("Nothing to delete")
      
    for config in semgrep_configs:
        if config["namespace"] in removed_configs and 'gitlab' in config['baseUrl']:
            call_semgrep_api(config, "DELETE")

    log_message("Script finished\n")

if __name__ == "__main__":
    main()
