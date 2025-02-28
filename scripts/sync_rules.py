import pandas as pd
import requests
import hashlib
import os

# 从指定文件中读取 URL 列表，忽略以 '#' 开头的注释行
def read_urls_from_file(file_path):
    urls = []
    # 以只读模式打开文件
    with open(file_path, 'r') as f:
        # 逐行读取文件内容
        for line in f:
            # 去除每行首尾的空白字符
            line = line.strip()
            # 只处理非空行且不以 '#' 开头的行
            if line and not line.startswith('#'):
                urls.append(line)
    return urls

# 如果映射文件存在且不为空，将其内容复制到临时映射文件中
def populate_temp_mapping_from_existing(temp_mapping_path, mapping_path):
    # 检查映射文件是否存在且文件大小大于 0
    if os.path.exists(mapping_path) and os.path.getsize(mapping_path) > 0:
        # 读取映射文件为 DataFrame 对象
        df_existing = pd.read_csv(mapping_path)
        # 将 DataFrame 对象写入临时映射文件，不包含行索引
        df_existing.to_csv(temp_mapping_path, index=False)

# 处理规则列表，根据当前规则列表更新临时映射文件
def process_rules_list(temp_mapping_path, urls):
    # 读取临时映射文件为 DataFrame 对象
    df = pd.read_csv(temp_mapping_path)
    # 获取临时映射文件中已有的 URL 集合
    existing_urls = set(df['URL'])

    # 移除不在规则列表中的条目
    df = df[df['URL'].isin(urls)]

    # 存储需要添加到临时映射文件的新条目
    new_entries = []
    # 遍历规则列表中的 URL
    for url in urls:
        # 如果 URL 不在已有的 URL 集合中
        if url not in existing_urls:
            # 将新 URL 添加到新条目列表中，其他字段初始化为空
            new_entries.append({'URL': url, 'RemoteFileName': '', 'LocalFileName': '', 'Hash': ''})

    # 如果有新条目需要添加
    if new_entries:
        # 将新条目列表转换为 DataFrame 对象
        new_df = pd.DataFrame(new_entries)
        # 将新的 DataFrame 对象与原 DataFrame 对象拼接，忽略原索引
        df = pd.concat([df, new_df], ignore_index=True)

    # 将更新后的 DataFrame 对象写入临时映射文件，不包含行索引
    df.to_csv(temp_mapping_path, index=False)

# 获取远程文件的文件名和哈希值，并更新到临时映射文件中
def fetch_remote_filenames_and_hashes(temp_mapping_path):
    # 读取临时映射文件为 DataFrame 对象
    df = pd.read_csv(temp_mapping_path)

    # 遍历 DataFrame 对象的每一行
    for index, row in df.iterrows():
        # 发送 HTTP 请求获取 URL 对应的内容
        response = requests.get(row['URL'])
        # 从 URL 中提取远程文件名
        remote_filename = row['URL'].split('/')[-1]
        # 计算响应内容的 MD5 哈希值
        hash_md5 = hashlib.md5(response.content).hexdigest()

        # 更新 DataFrame 对象中对应行的远程文件名和哈希值
        df.at[index, 'RemoteFileName'] = remote_filename
        df.at[index, 'Hash'] = hash_md5

    # 将更新后的 DataFrame 对象写入临时映射文件，不包含行索引
    df.to_csv(temp_mapping_path, index=False)

# 生成唯一的本地文件名，避免文件名冲突，并更新到临时映射文件中
def generate_unique_local_filenames(temp_mapping_path):
    # 读取临时映射文件为 DataFrame 对象
    df = pd.read_csv(temp_mapping_path)

    # 统计每个远程文件名的出现次数
    filename_counts = df['RemoteFileName'].value_counts()
    # 获取出现次数大于 1 的远程文件名列表
    duplicates = filename_counts[filename_counts > 1].index.tolist()

    # 遍历 DataFrame 对象的每一行
    for index, row in df.iterrows():
        # 获取当前行的远程文件名
        remote_filename = row['RemoteFileName']
        # 如果远程文件名在重复列表中
        if remote_filename in duplicates:
            # 分割 URL 为路径段列表
            parts = row['URL'].split('/')
            # 获取 URL 路径的倒数第二个部分作为唯一标识，如果路径段不足 2 个则为空
            unique_part = parts[-2] if len(parts) > 2 else ''
            # 生成唯一的本地文件名
            local_filename = f"{unique_part}-{remote_filename}"
        else:
            # 如果远程文件名不重复，直接使用远程文件名作为本地文件名
            local_filename = remote_filename

        # 更新 DataFrame 对象中对应行的本地文件名
        df.at[index, 'LocalFileName'] = local_filename

    # 将更新后的 DataFrame 对象写入临时映射文件，不包含行索引
    df.to_csv(temp_mapping_path, index=False)

# 下载或更新文件到指定目录，只保留最新版本
def download_or_update_files(temp_mapping_path, rules_dir):
    # 读取临时映射文件为 DataFrame 对象
    df = pd.read_csv(temp_mapping_path)
    # 存储需要删除的文件列表
    del_list = []

    # 遍历 DataFrame 对象的每一行
    for index, row in df.iterrows():
        # 生成本地文件的完整路径
        local_path = os.path.join(rules_dir, row['LocalFileName'])
        # 发送 HTTP 请求获取 URL 对应的内容
        response = requests.get(row['URL'])
        # 计算响应内容的 MD5 哈希值
        new_hash = hashlib.md5(response.content).hexdigest()

        # 如果本地文件已存在
        if os.path.exists(local_path):
            # 以二进制只读模式打开本地文件
            with open(local_path, 'rb') as f:
                # 计算本地文件内容的 MD5 哈希值
                existing_hash = hashlib.md5(f.read()).hexdigest()
            # 如果本地文件的哈希值与新的哈希值相同，说明文件未更新，跳过
            if existing_hash == new_hash:
                continue

        # 以二进制写入模式打开本地文件，将响应内容写入文件
        with open(local_path, 'wb') as f:
            f.write(response.content)

    # 将更新后的 DataFrame 对象写入临时映射文件，不包含行索引
    df.to_csv(temp_mapping_path, index=False)

# 清理旧文件，根据删除列表删除对应的文件
def clean_up_old_files(del_list_path):
    # 检查删除列表文件是否存在
    if os.path.exists(del_list_path):
        # 以只读模式打开删除列表文件
        with open(del_list_path, 'r') as f:
            # 逐行读取删除列表文件内容
            for line in f:
                # 去除每行首尾的空白字符
                file_to_delete = line.strip()
                # 检查文件是否存在，如果存在则删除
                if os.path.exists(file_to_delete):
                    os.remove(file_to_delete)

# 生成仓库中 rules 文件夹下文件的下载 URL 列表
def generate_local_rules_url_list(temp_mapping_path, repo_url):
    df = pd.read_csv(temp_mapping_path)
    # 以写入模式打开 url-local-rules.txt 文件，若文件不存在则创建
    with open('url-local-rules.txt', 'w') as f:
        for index, row in df.iterrows():
            local_filename = row['LocalFileName']
            # 构建文件的下载 URL
            url = f"{repo_url}/raw/refs/heads/main/rules/{local_filename}"
            f.write(url + '\n')

# 更新映射文件，将临时映射文件替换为正式映射文件，并删除删除列表文件
def update_mapping_files(temp_mapping_path, mapping_path, del_list_path):
    # 用临时映射文件替换正式映射文件
    os.replace(temp_mapping_path, mapping_path)
    # 如果删除列表文件存在，则删除
    if os.path.exists(del_list_path):
        os.remove(del_list_path)

# 主函数，协调各个步骤的执行
def main():
    # 临时映射文件的路径
    temp_mapping_path = 'temp_mapping.csv'
    # 正式映射文件的路径
    mapping_path = 'mapping.csv'
    # 删除列表文件的路径
    del_list_path = 'del_list.txt'
    # 规则文件存储目录
    rules_dir = 'rules'
    # 规则列表文件的路径
    rules_list_path = 'rules-list.txt'
    # 仓库的 URL，根据实际情况修改
    repo_url = 'https://github.com/chisenin/rules-template'

    # 创建规则文件存储目录，如果目录已存在则不报错
    os.makedirs(rules_dir, exist_ok=True)
    # 以写入模式打开临时映射文件，写入文件头
    with open(temp_mapping_path, 'w') as f:
        f.write("URL,RemoteFileName,LocalFileName,Hash\n")

    # 从规则列表文件中读取 URL 列表
    urls = read_urls_from_file(rules_list_path)
    # 如果 URL 列表为空，则直接返回
    if not urls:
        return

    # 从现有映射文件中填充临时映射文件
    populate_temp_mapping_from_existing(temp_mapping_path, mapping_path)
    # 处理规则列表，更新临时映射文件
    process_rules_list(temp_mapping_path, urls)
    # 获取远程文件的文件名和哈希值，更新临时映射文件
    fetch_remote_filenames_and_hashes(temp_mapping_path)
    # 生成唯一的本地文件名，更新临时映射文件
    generate_unique_local_filenames(temp_mapping_path)
    # 下载或更新文件到指定目录，只保留最新版本
    download_or_update_files(temp_mapping_path, rules_dir)
    # 清理旧文件
    clean_up_old_files(del_list_path)
    # 生成仓库中 rules 文件夹下文件的下载 URL 列表
    generate_local_rules_url_list(temp_mapping_path, repo_url)
    # 更新映射文件
    update_mapping_files(temp_mapping_path, mapping_path, del_list_path)

if __name__ == "__main__":
    main()
