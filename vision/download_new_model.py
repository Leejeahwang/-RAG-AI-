import subprocess
import os
import shutil
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(BASE_DIR, "temp_git")
MODELS_DIR = os.path.join(BASE_DIR, "models")

def run_cmd(cmd, cwd=None):
    print(f"Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error: {res.stderr}")
        return False
    print(res.stdout)
    return True

def main():
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
        
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    # 1. Clone the repository
    clone_cmd = ["git", "clone", "https://github.com/imnuman/fire-detection-yolo.git", TEMP_DIR]
    if not run_cmd(clone_cmd):
        print("❌ Git clone failed.")
        return
        
    # 2. Check and run the weights download script
    script_path = os.path.join(TEMP_DIR, "scripts", "download_weights.py")
    if not os.path.exists(script_path):
        # Fallback to search in root if structure is different
        script_path = os.path.join(TEMP_DIR, "download_weights.py")
        
    if not os.path.exists(script_path):
        print(f"⚠️ Download script not found.")
        # Let's inspect the temp dir files
        print(os.listdir(TEMP_DIR))
        return
        
    print(f"✅ Found download script at: {script_path}")
    
    # Run download weights script using current python environment (with necessary packages)
    python_exe = sys.executable
    download_cmd = [python_exe, script_path]
    run_cmd(download_cmd, cwd=TEMP_DIR)
    
    # 3. Find and copy .pt files
    pt_files = []
    for root, dirs, files in os.walk(TEMP_DIR):
        for f in files:
            if f.endswith(".pt"):
                pt_files.append(os.path.join(root, f))
                
    if not pt_files:
        print("❌ No .pt files found in cloned directory after running the download script.")
        # Print script content for troubleshooting
        try:
            with open(script_path, "r", encoding="utf-8") as sf:
                print("--- Script Contents ---")
                print(sf.read())
                print("-----------------------")
        except Exception as e:
            print(f"Cannot read script: {e}")
        return
        
    print(f"🎉 Found .pt files: {pt_files}")
    for pt in pt_files:
        # Standardize the name to avoid conflicts
        dest_name = f"new_yolov8n_{os.path.basename(pt)}"
        if "best" in os.path.basename(pt).lower():
            dest_name = "new_yolov8n_best.pt"
            
        dest_path = os.path.join(MODELS_DIR, dest_name)
        shutil.copy2(pt, dest_path)
        print(f"✅ Copied {pt} to {dest_path}")
        
    # 4. Clean up
    try:
        shutil.rmtree(TEMP_DIR)
        print("🧹 Temporary directories cleaned up successfully.")
    except Exception as e:
        print(f"⚠️ Cleanup failed: {e}")

if __name__ == "__main__":
    main()
