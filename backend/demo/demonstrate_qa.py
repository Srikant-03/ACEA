
import asyncio
import os
import sys
import threading
import time
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, HTTPServer
from app.agents.browser_validation_agent import BrowserValidationAgent

PORT = 8081

class SilentHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

def run_server():
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, SilentHandler)
    # print(f"Serving at port {PORT}")
    httpd.serve_forever()

async def run_demo(url, project_path):
    print(f"Starting browser validation check on {url}")
    
    agent = BrowserValidationAgent()
    
    # Run comprehensive validation
    report = await agent.comprehensive_validate(
        url=url,
        project_path=project_path,
        validation_level="thorough"
    )
    return report

if __name__ == "__main__":
    # 1. Start static server
    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    
    # Give server a moment to start
    time.sleep(1)
    
    # 2. Setup test environment
    # Use current directory or backend/demo
    base_dir = Path("demo").absolute()
    url = f"http://localhost:{PORT}/demo/low_contrast.html"
    
    # Create dummy prompt.txt for alignment testing
    prompt_path = base_dir / "prompt.txt"
    try:
        prompt_path.write_text("Build a perfect, bug-free landing page for 'CloudSync' with a clean, modern design and NO overlapping elements.", encoding="utf-8")
        print(f"Created dummy prompt at {prompt_path}")
    except Exception as e:
        print(f"Failed to write prompt file: {e}")

    # 3. Run validation
    try:
        print("Running validation (this may take 15-30 seconds)...")
        report = asyncio.run(run_demo(url, str(base_dir)))
        
        print(f"\nDEBUG: Report keys: {report.keys()}")
        if 'visual_overlap' in report['tests']:
             print(f"\nDEBUG: Visual Overlap Result: {report['tests']['visual_overlap']}")
        else:
             print("\nDEBUG: Visual Overlap Key MISSING from report['tests']")
             
        # 4. Write Report
        with open("demo_report.txt", "w", encoding="utf-8") as f:
            f.write("=== BROWSER VALIDATION REPORT ===\n")
            f.write(f"URL: {report['url']}\n")
            f.write(f"Timestamp: {report['timestamp']}\n")
            f.write(f"Overall Score: {report['scores'].get('overall', 'N/A')}/100\n")
            f.write(f"Status: {report['overall_status']}\n\n")
            
            f.write("--- SCORES ---\n")
            for cat, score in report['scores'].items():
                f.write(f"{str(cat).ljust(20)}: {score}\n")
            
            f.write("\n--- ISSUES ---\n")
            for test_name, result in report['tests'].items():
                status = result.get('status', 'UNKNOWN')
                issues = result.get('issues', [])
                
                f.write(f"\n[{test_name.upper()}] Status: {status}\n")
                
                if issues:
                    for issue in issues:
                        f.write(f" - {issue}\n")
                else:
                    f.write(" - No issues found.\n")
                    
                # Special fields
                if test_name == 'visual_overlap' and result.get('overlaps'):
                    f.write(f"   (Found {len(result['overlaps'])} overlap instances)\n")
                
                if test_name == 'prompt_alignment':
                    f.write(f"   Alignment Score: {result.get('alignment_score')}\n")
                    if result.get('change_log'):
                         f.write(f"   Changes Detected: {result.get('change_log')}\n")

        print("\n✅ Verification Complete!")
        print(f"Report written to demo_report.txt")
        print(f"Overall Status: {report['overall_status']}")
        
    except Exception as e:
        print(f"\n❌ Error running demo: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        if prompt_path.exists():
            prompt_path.unlink()
            print("Cleaned up prompt.txt")
        # Server thread dies with main process
