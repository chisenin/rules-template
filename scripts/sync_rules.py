import pandas as pd
import requests
import hashlib
import os

def read_urls_from_file(file_path):
    urls = []
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                urls.append(line)
    return urls

def populate_temp_mapping_from_existing(temp_mapping_path, mapping_path):
    if os.path.exists(mapping_path) and os.path.getsize(mapping_path) > 0:
        df_existing = pd.read_csv(mapping_path)
        df_existing.to_csv(temp_mapping_path, index=False)

def process_rules_list(temp_mapping_path, urls):
    df = pd.read_csv(temp_mapping_path)
    existing_urls = set(df['URL'])

    # Remove entries not in rules-list.txt
    df = df[df['URL'].isin(urls)]

    # Add new entries to temp_mapping.csv
    new_entries = []
    for url in urls:
        if url not in existing_urls:
            new_entries.append({'URL': url, 'RemoteFileName': '', 'LocalFileName': '', 'Hash': ''})

    if new_entries:
        new_df = pd.DataFrame(new_entries)
        df = pd.concat([df, new_df], ignore_index=True)

    df.to_csv(temp_mapping_path, index=False)

def fetch_remote_filenames_and_hashes(temp_mapping_path):
    df = pd.read_csv(temp_mapping_path)

    for index, row in df.iterrows():
        response = requests.get(row['URL'])
        remote_filename = row['URL'].split('/')[-1]
        hash_md5 = hashlib.md5(response.content).hexdigest()

        df.at[index, 'RemoteFileName'] = remote_filename
        df.at[index, 'Hash'] = hash_md5

    df.to_csv(temp_mapping_path, index=False)

def generate_unique_local_filenames(temp_mapping_path):
    df = pd.read_csv(temp_mapping_path)

    filename_counts = df['RemoteFileName'].value_counts()
    duplicates = filename_counts[filename_counts > 1].index.tolist()

    for index, row in df.iterrows():
        remote_filename = row['RemoteFileName']
        if remote_filename in duplicates:
            parts = row['URL'].split('/')
            unique_part = parts[-2] if len(parts) > 2 else ''
            local_filename = f"{unique_part}-{remote_filename}"
        else:
            local_filename = remote_filename

        df.at[index, 'LocalFileName'] = local_filename

    df.to_csv(temp_mapping_path, index=False)

def download_or_update_files(temp_mapping_path, rules_dir):
    df = pd.read_csv(temp_mapping_path)
    del_list = []

    for index, row in df.iterrows():
        local_path = os.path.join(rules_dir, row['LocalFileName'])
        response = requests.get(row['URL'])
        new_hash = hashlib.md5(response.content).hexdigest()

        if os.path.exists(local_path):
            with open(local_path, 'rb') as f:
                existing_hash = hashlib.md5(f.read()).hexdigest()
            if existing_hash == new_hash:
                continue

        with open(local_path, 'wb') as f:
            f.write(response.content)

    df.to_csv(temp_mapping_path, index=False)

def clean_up_old_files(del_list_path):
    if os.path.exists(del_list_path):
        with open(del_list_path, 'r') as f:
            for line in f:
                file_to_delete = line.strip()
                if os.path.exists(file_to_delete):
                    os.remove(file_to_delete)

def update_mapping_files(temp_mapping_path, mapping_path, del_list_path):
    os.replace(temp_mapping_path, mapping_path)
    if os.path.exists(del_list_path):
        os.remove(del_list_path)

def main():
    temp_mapping_path = 'temp_mapping.csv'
    mapping_path = 'mapping.csv'
    del_list_path = 'del_list.txt'
    rules_dir = 'rules'
    rules_list_path = 'rules-list.txt'

    os.makedirs(rules_dir, exist_ok=True)
    with open(temp_mapping_path, 'w') as f:
        f.write("URL,RemoteFileName,LocalFileName,Hash\n")

    urls = read_urls_from_file(rules_list_path)
    if not urls:
        return

    populate_temp_mapping_from_existing(temp_mapping_path, mapping_path)
    process_rules_list(temp_mapping_path, urls)
    fetch_remote_filenames_and_hashes(temp_mapping_path)
    generate_unique_local_filenames(temp_mapping_path)
    download_or_update_files(temp_mapping_path, rules_dir)
    clean_up_old_files(del_list_path)
    update_mapping_files(temp_mapping_path, mapping_path, del_list_path)

if __name__ == "__main__":
    main()
