import tempfile
from pathlib import Path

from facturx.facturx import generate_from_file


def embed_facturx(pdf_bytes: bytes, xml_bytes: bytes) -> bytes:
    """
    Takes a normal PDF bytes + Factur-X XML bytes
    Returns a new PDF bytes with the XML embedded (Factur-X PDF/A-3).
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        in_pdf = tmp_dir / "in.pdf"
        in_xml = tmp_dir / "factur-x.xml"
        out_pdf = tmp_dir / "out_facturx.pdf"

        in_pdf.write_bytes(pdf_bytes)
        in_xml.write_bytes(xml_bytes)

        # facturx library writes the output PDF file
        generate_from_file(str(in_pdf), str(in_xml), output_pdf_file=str(out_pdf))

        return out_pdf.read_bytes()
