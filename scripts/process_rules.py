import os
import hashlib
import subprocess
import csv

RULES_LIST_PATH = os.getenv('RULES_LIST_PATH', 'rules-list.txt')
MAPPING_FILE_PATH = os.getenv('MAPPING_FILE_PATH', 'mapping.csv')
TEMP_MAPPING_FILE_PATH = os.getenv('TEMP_MAPPING_FILE_PATH', 'temp_mapping.csv')
DEL_LIST_FILE_PATH = os.getenv('DEL_LIST_FILE_PATH', 'del_list.txt')
RULES_DIR_PATH = os.getenv('RULES_DIR_PATH', 'rules')

def read_file_lines(file_path):
    with open(file_path, 'r') as file:
        return file.readlines()

def write_csv(file_path, rows, mode='w', header=None):
    with open(file_path, mode, newline='') as file:
        writer = csv.writer(file)
        if header:
            writer.writerow(header)
        for row in rows:
            writer.writerow(row)

def create_temp_mapping():
    header = ["URL", "RemoteFileName", "LocalFileName", "Hash"]
    existing_rows = []
    if os.path.exists(MAPPING_FILE_PATH) and os.path.getsize(MAPPING_FILE_PATH) > 0:
        with open(MAPPING_FILE_PATH, mode='r') as file:
            reader = csv.reader(file)
            existing_rows = list(reader)

    write_csv(TEMP_MAPPING_FILE_PATH, existing_rows, header=header)

def process_url_list():
    urls = read_file_lines(RULES_LIST_PATH)
    new_rows = []
    for url in urls:
        url = url.strip()
        if not url or url.startswith('#'):
            continue

        if any(url in row for row in new_rows):
            continue

        if not any(url in row for row in read_file_lines(TEMP_MAPPING_FILE_PATH)):
            new_row = [url, '', '', '']
            new_rows.append(new_row)

    existing_rows = read_file_lines(TEMP_MAPPING_FILE_PATH)
    all_rows = existing_rows + new_rows

    # Write the updated temp_mapping.csv
    write_csv(TEMP_MAPPING_FILE_PATH, all_rows)

def generate_del_list():
    existing_urls = set(url.split(',')[0] for url in read_file_lines(TEMP_MAPPING_FILE_PATH)[1:])
    new_urls = set(url.strip() for url in read_file_lines(RULES_LIST_PATH) if url.strip() and not url.startswith('#'))

    urls_to_remove = existing_urls - new_urls
    del_rows = []
    new_temp_rows = []

    with open(TEMP_MAPPING_FILE_PATH, 'r') as file:
        reader = csv.reader(file)
        header = next(reader)
        new_temp_rows.append(header)
        for row in reader:
            if row[0] in urls_to_remove:
                del_rows.append(row[2])  # LocalFileName
            else:
                new_temp_rows.append(row)

    write_csv(TEMP_MAPPING_FILE_PATH, new_temp_rows, mode='w')
    write_csv(DEL_LIST_FILE_PATH, [[row] for row in del_rows], mode='w')

def handle_empty_mapping():
    if not os.path.exists(MAPPING_FILE_PATH) or os.path.getsize(MAPPING_FILE_PATH) == 0:
        write_csv(TEMP_MAPPING_FILE_PATH, [["URL", "RemoteFileName", "LocalFileName", "Hash"]])
    else:
        write_csv(TEMP_MAPPING_FILE_PATH, read_file_lines(MAPPING_FILE_PATH))
        with open(MAPPING_FILE_PATH, 'r') as file:
            reader = csv.reader(file)
            next(reader)  # Skip header
            del_rows = [row[2] for row in reader]  # LocalFileName
        write_csv(DEL_LIST_FILE_PATH, [[row] for row in del_rows], mode='w')

def process_filenames_and_generate_local_names():
    temp_mapping = read_file_lines(TEMP_MAPPING_FILE_PATH)
    header = temp_mapping[0].strip().split(',')
    rows = [row.strip().split(',') for row in temp_mapping[1:]]

    remote_file_counts = {}
    for row in rows:
        if len(row) < 2:
            print(f"Skipping invalid row: {row}")
            continue
        remote_filename = row[1]
        if remote_filename in remote_file_counts:
            remote_file_counts[remote_filename] += 1
        else:
            remote_file_counts[remote_filename] = 1

    tracked_remote_files = {k for k, v in remote_file_counts.items() if v > 1}

    new_rows = []
    for row in rows:
        if len(row) < 2:
            print(f"Skipping invalid row: {row}")
            continue
        url, remote_filename, local_filename, hash_value = row
        if remote_filename in tracked_remote_files:
            url_parts = url.rstrip('/').split('/')
            url_path_second_last = url_parts[-2] if len(url_parts) > 1 else ''
            local_filename = f"{url_path_second_last}-{remote_filename}"
        else:
            local_filename = remote_filename

        new_row = [url, remote_filename, local_filename, hash_value]
        new_rows.append(new_row)

    write_csv(TEMP_MAPPING_FILE_PATH, [header] + new_rows, mode='w')

def download_and_update_files():
    temp_mapping = read_file_lines(TEMP_MAPPING_FILE_PATH)
    header = temp_mapping[0].strip().split(',')
    rows = [row.strip().split(',') for row in temp_mapping[1:]]

    for row in rows:
        if len(row) < 2:
            print(f"Skipping invalid row: {row}")
            continue
        url, remote_filename, local_filename, old_hash = row
        file_path = os.path.join(RULES_DIR_PATH, local_filename)

        if remote_filename.endswith('.srs'):
            try:
                response = subprocess.check_output(['wget', '-nv', '-O', '-', url], timeout=10)
                with open(file_path, 'wb') as file:
                    file.write(response[:1472])
                new_hash = hashlib.sha256(response[:1472]).hexdigest()
            except subprocess.CalledProcessError:
                print(f"Failed to download {url}")
                continue
        elif remote_filename.endswith(('.json', '.yaml', '.yml')):
            try:
                subprocess.run(['wget', '-nv', '-O', file_path, url], check=True, timeout=10)
                with open(file_path, 'rb') as file:
                    new_hash = hashlib.sha256(file.read()).hexdigest()
            except subprocess.CalledProcessError:
                print(f"Failed to download {url}")
                continue
        else:
            print(f"Unsupported file type: {remote_filename}")
            continue

        if old_hash != new_hash:
            print(f"Updating {local_filename} (Hash: {new_hash})")
            row[3] = new_hash

    write_csv(TEMP_MAPPING_FILE_PATH, [header] + rows, mode='w')

def clean_up_old_files():
    del_list = read_file_lines(DEL_LIST_FILE_PATH)
    for file_to_delete in del_list:
        file_path = os.path.join(RULES_DIR_PATH, file_to_delete.strip())
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Deleted {file_to_delete.strip()}")

def update_mapping_file_and_remove_temp_files():
    subprocess.run(['cp', TEMP_MAPPING_FILE_PATH, MAPPING_FILE_PATH], check=True)
    for temp_file in [TEMP_MAPPING_FILE_PATH, DEL_LIST_FILE_PATH]:
        if os.path.exists(temp_file):
            os.remove(temp_file)

def main():
    create_temp_mapping()
    if os.path.exists(RULES_LIST_PATH) and os.path.getsize(RULES_LIST_PATH) > 0:
        process_url_list()
        generate_del_list()
    else:
        handle_empty_mapping()
    
    process_filenames_and_generate_local_names()
    download_and_update_files()
    clean_up_old_files()
    update_mapping_file_and_remove_temp_files()

if __name__ == "__main__":
    main()
