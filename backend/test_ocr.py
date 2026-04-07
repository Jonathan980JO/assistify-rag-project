from pdf2image import convert_from_path
import pytesseract
from pathlib import Path

# Path to the actual PDF and page number, adjusting it to be run from the backend directory
pdf_path = Path(r"G:\Grad_Project\assistify-rag-project-main\backend\assets\02bdcc93_Cyper_Knowledge_test.pdf")

try:
    print(f"Testing OCR on: {pdf_path.name}")
    print("Converting page 1 to an image...")
    
    # We test page 1 first as requested
    images = convert_from_path(str(pdf_path), first_page=1, last_page=1)
    
    if images:
        print("Success! PDF converted to image via poppler.")
        print("Running Tesseract OCR on the image...")
        
        text = pytesseract.image_to_string(images[0])
        
        print("\n--- Extracted Text ---")
        if text.strip():
            print(text.strip())
        else:
            print("[Text is empty - page might be blank or Tesseract couldn't read it]")
        print("----------------------")
        
    else:
        print("Error: No images were returned.")

except Exception as e:
    print(f"\n[!] OCR Test Failed: {e}")
