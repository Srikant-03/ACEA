
import subprocess
import sys

def run_tests():
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-v", "tests/test_thought_signatures.py"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_tests()
