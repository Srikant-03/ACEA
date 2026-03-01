
import glob
import re
import os

def check_files():
    # os.walk to find all py files
    files = []
    for root, dirs, files_list in os.walk("backend/app"):
        for file in files_list:
            if file.endswith(".py"):
                files.append(os.path.join(root, file))
    
    # Regex for f-string with quote inside format spec
    # Look for: f" ... { ... : " ... " } ... "
    # This is hard to regex perfectly, but look for : " inside a line with f"
    pattern = re.compile(r'f".*\{.*:\s*[\'"].*\}')
    
    print(f"Scanning {len(files)} files...")
    
    for f_path in files:
        try:
            with open(f_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
                for i, line in enumerate(lines):
                    if pattern.search(line):
                        print(f"MATCH: {f_path}:{i+1}")
                        print(f"  {line.strip()}")
        except Exception as e:
            print(f"Error reading {f_path}: {e}")

if __name__ == "__main__":
    check_files()
