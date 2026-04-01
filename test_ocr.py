import easyocr
import numpy as np
from PIL import Image
import os

def test_ocr():
    print("Testing EasyOCR...")
    try:
        reader = easyocr.Reader(['ko', 'en'])
        print("Reader initialized successfully.")
        # Create a small dummy image with text if possible, or just print success
        print("EasyOCR is ready for use.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_ocr()
