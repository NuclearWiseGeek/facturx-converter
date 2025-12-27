from pathlib import Path
from facturx import generate_from_file

def main():
    base_dir = Path(__file__).parent

    pdf_path = base_dir / "input" / "sample_invoice.pdf"
    xml_path = base_dir / "input" / "sample_invoice.xml"
    out_path = base_dir / "output" / "sample_invoice_facturx.pdf"

    if not pdf_path.exists():
        print("❌ Missing:", pdf_path)
        return

    if not xml_path.exists():
        print("❌ Missing:", xml_path)
        return

    out_path.parent.mkdir(exist_ok=True)

    print("🔧 Embedding XML into PDF...")
    generate_from_file(str(pdf_path), str(xml_path), output_pdf_file=str(out_path))

    print("✅ Done! Created:", out_path)

if __name__ == "__main__":
    main()
