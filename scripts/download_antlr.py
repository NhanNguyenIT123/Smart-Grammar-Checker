import urllib.request
import os
from pathlib import Path

JAR_URL = "https://www.antlr.org/download/antlr-4.13.2-complete.jar"
DEST_PATH = Path(__file__).resolve().parents[1] / "backend" / "antlr-4.13.2-complete.jar"

def download_jar():
    print(f"Downloading ANTLR complete jar from {JAR_URL}...")
    print(f"Destination: {DEST_PATH}")
    
    # Create parents if they don't exist
    DEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # Download
    urllib.request.urlretrieve(JAR_URL, DEST_PATH)
    print("Download completed successfully!")

if __name__ == "__main__":
    download_jar()
