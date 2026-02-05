
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
