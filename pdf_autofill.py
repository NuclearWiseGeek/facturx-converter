import io
import re
from datetime import datetime, date
from pypdf import PdfReader

# --- IMPORTS: We use the standard library now ---
try:
    from azure.core.credentials import AzureKeyCredential
    from azure.ai.formrecognizer import DocumentAnalysisClient
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False
    print("⚠️ Azure library not found. Run: pip install azure-ai-formrecognizer")


# --- HELPER: Fix dates ---
def _parse_date(s):
    if not s: return None
    # If it's already a date object, just return it
    if isinstance(s, (date, datetime)):
        return s
    
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None


# --- TEXT FALLBACK ---
def extract_fields_text(pdf_bytes: bytes) -> dict:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        text = ""

    data = {}
    # Basic Regex Patterns
    m = re.search(r"Invoice\s*(No|Number|ID)\s*[:\-]?\s*([A-Z0-9\-\/]+)", text, re.I)
    if m: data["invoice_number"] = m.group(2)
    
    m = re.search(r"Invoice\s*Date\s*[:\-]?\s*(\d{4}[-/]\d{2}[-/]\d{2})", text, re.I)
    if m: data["invoice_date"] = _parse_date(m.group(1))
    
    m = re.search(r"(Customer|Buyer)\s*[:\-]?\s*(.+)", text, re.I)
    if m: data["buyer_name"] = m.group(2).strip()
    
    m = re.search(r"(Subtotal|Total\s*HT)\s*[:\-]?\s*([0-9]+[.,][0-9]{2})", text, re.I)
    if m: data["total_ht_str"] = m.group(2).replace(",", ".")

    return data


# --- AZURE OCR (Standard Version) ---
def azure_extract_invoice_fields(pdf_bytes: bytes, endpoint: str, key: str) -> dict:
    if not AZURE_AVAILABLE:
        print("❌ Azure library missing.")
        return {}

    if not endpoint or not key:
        print("❌ Missing Endpoint/Key.")
        return {}

    try:
        # 1. Client Setup
        credential = AzureKeyCredential(key)
        client = DocumentAnalysisClient(endpoint=endpoint, credential=credential)

        # 2. Analyze
        poller = client.begin_analyze_document(
            "prebuilt-invoice", 
            document=pdf_bytes
        )
        result = poller.result()

        if not result.documents:
            return {}

        invoice = result.documents[0]
        fields = invoice.fields
        out = {}

        # 3. Helper to extract values
        def get_val(field_name):
            f = fields.get(field_name)
            if not f: return None
            # Return the specialized value if possible
            return f.value

        # 4. Extract
        out["invoice_number"] = get_val("InvoiceId")
        out["seller_name"] = get_val("VendorName")
        out["buyer_name"] = get_val("CustomerName")
        
        # Dates are usually returned as objects, but we normalize them
        out["invoice_date"] = _parse_date(get_val("InvoiceDate"))

        # Money Fields (The object usually has .amount and .symbol)
        total_ht_field = fields.get("SubTotal")
        if total_ht_field and total_ht_field.value:
            # Handle currency object safely
            if hasattr(total_ht_field.value, 'amount'):
                out["total_ht_str"] = str(total_ht_field.value.amount)
                out["currency"] = getattr(total_ht_field.value, 'symbol', 'EUR')
            else:
                # Fallback if it's just a number
                out["total_ht_str"] = str(total_ht_field.value)

        total_ttc_field = fields.get("InvoiceTotal")
        if total_ttc_field and total_ttc_field.value:
             if hasattr(total_ttc_field.value, 'amount'):
                out["total_ttc_str"] = str(total_ttc_field.value.amount)
             else:
                out["total_ttc_str"] = str(total_ttc_field.value)

        # Remove empty keys
        return {k: v for k, v in out.items() if v}

    except Exception as e:
        print(f"Azure Error: {e}")
        return {}