import subprocess
import time
import psutil
import os

def open_chrome():
    print("Opening Chrome browser...")
    # Windows-only: Launch Chrome
    subprocess.Popen(["start", "chrome"], shell=True)
    time.sleep(5)  # wait 5 seconds for it to open

def close_chrome():
    print("Closing all Chrome processes...")
    closed = 0
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] and 'chrome' in proc.info['name'].lower():
                proc.terminate()
                closed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    print(f"Closed {closed} Chrome process(es).")

if __name__ == "__main__":
    open_chrome()
    close_chrome()
