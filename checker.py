
from re import findall

def extract_and_append_unique_configs(input_path="RawText.txt", output_path="Final_Configs.txt"):
    with open(input_path, "r", encoding="utf-8") as f:
        full = f.read()

    pattern = r"(?:vless|trojan|ss)://[^\s#]+"
    links = findall(pattern, full)

    try:
        with open(output_path, "r", encoding="utf-8") as f:
            existing = set(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        existing = set()

    new_count = 0
    with open(output_path, "a", encoding="utf-8") as f:
        for link in links:
            if link not in existing:
                f.write(link + "\n")
                existing.add(link)
                new_count += 1

    return new_count, len(existing)
def remove_duplicate_configs(input_file, output_file):
    """
    Reads configuration file, removes duplicates, and saves unique configurations.
    
    Args:
        input_file: Path to the input file
        output_file: Path to save the output file
    """
    
    with open(input_file, 'r') as file:
        lines = file.readlines()
    
    clean_lines = [line.strip() for line in lines if line.strip()]
    
    unique_configs = set()
    
    for config in clean_lines:
        unique_configs.add(config)
    
    with open(output_file, 'w') as file:
        for config in unique_configs:
            file.write(config + '\n')
    
    print(f"Original configurations: {len(clean_lines)}")
    print(f"Unique configurations: {len(unique_configs)}")
    print(f"Duplicates removed: {len(clean_lines) - len(unique_configs)}")
    print(f"Unique configurations saved to: {output_file}")

