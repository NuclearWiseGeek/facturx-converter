import os
import io
from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient


def main():
    load_dotenv()

    endpoint = os.getenv("DOCUMENTINTELLIGENCE_ENDPOINT")
    key = os.getenv("DOCUMENTINTELLIGENCE_API_KEY")

    if not endpoint or not key:
        print("❌ Missing DOCUMENTINTELLIGENCE_ENDPOINT or DOCUMENTINTELLIGENCE_API_KEY in .env")
        return

    client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))

    pdf_path = r"input\sample_invoice.pdf"   # <-- use your real pdf path if different
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    poller = client.begin_analyze_document(
        model_id="prebuilt-invoice",
        body=io.BytesIO(pdf_bytes),
    )
    result = poller.result()

    if not result.documents:
        print("❌ No invoice document detected")
        return

    doc = result.documents[0]
    fields = doc.fields or {}

    print("\n✅ Azure extracted fields:")
    for k, v in fields.items():
        # v has value + confidence, we just print "content" (what Azure saw)
        try:
            content = v.get("content")
        except Exception:
            content = str(v)
        print(f"- {k}: {content}")


if __name__ == "__main__":
    main()
