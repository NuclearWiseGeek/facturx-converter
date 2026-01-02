import os
from dotenv import load_dotenv
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential

# 1. Load your local secrets
load_dotenv()
endpoint = os.getenv("DOCUMENTINTELLIGENCE_ENDPOINT")
key = os.getenv("DOCUMENTINTELLIGENCE_API_KEY")

def analyze_lines(pdf_path):
    print(f"🔍 Analyzing {pdf_path} for Line Items...")
    
    # Connect to Azure
    client = DocumentAnalysisClient(endpoint=endpoint, credential=AzureKeyCredential(key))
    
    with open(pdf_path, "rb") as f:
        # We use the "prebuilt-invoice" model which is great at tables
        poller = client.begin_analyze_document("prebuilt-invoice", document=f)
        result = poller.result()

    # 2. Loop through the items
    print("\n--- EXTRACTED ITEMS ---")
    
    # Invoices usually have one main table. We look for 'Items'.
    for idx, doc in enumerate(result.documents):
        if "Items" in doc.fields:
            items = doc.fields["Items"].value
            for i, item in enumerate(items):
                row = item.value
                # Try to grab common columns
                desc = row.get("Description")
                qty = row.get("Quantity")
                price = row.get("UnitPrice")
                total = row.get("Amount")
                
                # Print clean text if found
                d_txt = desc.value if desc else "No Desc"
                q_txt = qty.value if qty else "1"
                p_txt = price.value if price else "0"
                t_txt = total.value if total else "0"
                
                print(f"Row {i+1}: {d_txt} | Qty: {q_txt} | Price: {p_txt} | Total: {t_txt}")
        else:
            print("⚠️ No 'Items' table found in this invoice.")

# --- RUN IT ---
# Change this filename to your actual PDF name!
pdf_name = "sample_invoice.pdf" 

if __name__ == "__main__":
    if not endpoint or not key:
        print("❌ Error: Keys not found. Check your .env file.")
    else:
        analyze_lines(pdf_name)