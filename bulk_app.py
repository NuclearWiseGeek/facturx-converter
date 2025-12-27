import streamlit as st
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import io
import os
import re
import zipfile
import json

from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient

from facturx_engine import embed_facturx
from facturx_xml import build_facturx_minimum_xml
from validator import validate_facturx_minimum

from pdf_autofill import extract_fields as extract_fields_text


# -------------------------
# Free plan monthly limit
# -------------------------
FREE_LIMIT_PER_MONTH = 5
USAGE_FILE = Path("output") / "usage.json"

DEV_RESET_CODE = "DEV310899"  # ✅ your requested code


def current_month_key() -> str:
    return datetime.now().strftime("%Y-%m")  # ex: "2025-12"


def load_usage() -> dict:
    try:
        if USAGE_FILE.exists():
            return json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def save_usage(data: dict):
    USAGE_FILE.parent.mkdir(exist_ok=True)
    USAGE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_month_count(data: dict, month_key: str) -> int:
    return int(data.get("months", {}).get(month_key, 0))


def increment_month_count(data: dict, month_key: str, n: int):
    if "months" not in data:
        data["months"] = {}
    data["months"][month_key] = get_month_count(data, month_key) + n


# -------------------------
# Helpers
# -------------------------
def safe_name(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "invoice"
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s)
    return s[:80]


def to_decimal(s):
    if s is None:
        return None
    try:
        return Decimal(str(s).replace(",", "."))
    except Exception:
        return None


def compute_vat_rate_percent(total_ht: Decimal, total_ttc: Decimal):
    if total_ht is None or total_ttc is None:
        return None
    if total_ht <= 0 or total_ttc < total_ht:
        return None
    vat_amount = total_ttc - total_ht
    rate = (vat_amount / total_ht * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return rate


def azure_extract_invoice_fields(pdf_bytes: bytes) -> dict:
    load_dotenv()
    endpoint = os.getenv("DOCUMENTINTELLIGENCE_ENDPOINT")
    key = os.getenv("DOCUMENTINTELLIGENCE_API_KEY")

    if not endpoint or not key:
        raise RuntimeError("Missing DOCUMENTINTELLIGENCE_ENDPOINT or DOCUMENTINTELLIGENCE_API_KEY in .env")

    client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))

    poller = client.begin_analyze_document(
        model_id="prebuilt-invoice",
        body=io.BytesIO(pdf_bytes),
    )
    result = poller.result()

    if not result.documents:
        return {}

    doc = result.documents[0]
    fields = doc.fields or {}

    def content(name: str):
        f = fields.get(name)
        if not f:
            return None
        try:
            return f.get("content")
        except Exception:
            return None

    def number(name: str):
        f = fields.get(name)
        if not f:
            return None
        try:
            vc = f.get("valueCurrency")
            if isinstance(vc, dict) and "amount" in vc:
                return str(vc["amount"])
        except Exception:
            pass
        return content(name)

    inv_date_raw = content("InvoiceDate")
    inv_date = None
    if inv_date_raw:
        try:
            inv_date = datetime.strptime(inv_date_raw.strip(), "%Y-%m-%d").date()
        except Exception:
            inv_date = None

    return {
        "invoice_number": content("InvoiceId") or content("InvoiceNumber"),
        "invoice_date": inv_date,
        "buyer_name": content("CustomerName"),
        "seller_name": content("VendorName"),
        "total_ht_str": number("SubTotal"),
        "total_ttc_str": number("InvoiceTotal"),
    }


# -------------------------
# UI
# -------------------------
st.set_page_config(page_title="Factur-X Bulk Converter", layout="centered")
st.title("Factur-X Bulk Converter (Local Demo)")
st.caption("Bulk mode: upload many PDFs → download one ZIP with PDFs + XML + reports.")

use_azure = st.checkbox("Use Azure OCR (best results, may cost money later)", value=True)
azure_confirm = st.checkbox("I understand Azure OCR may cost money", value=False)

# ---- DEV tools + PRO unlock ----
st.subheader("Developer tools (DEV only)")

dev_code = st.text_input("Type DEV code to unlock DEV tools", type="password", placeholder="(ask developer)")
dev_unlocked = (dev_code == DEV_RESET_CODE)

pro_mode = False
if dev_unlocked:
    pro_mode = st.checkbox("⭐ PRO mode (unlimited conversions)", value=False)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔁 Reset free usage (DEV only)"):
            try:
                if USAGE_FILE.exists():
                    USAGE_FILE.unlink()
                st.success("✅ Usage reset! Refresh the page.")
            except Exception as e:
                st.error(f"Could not reset usage: {e}")

    with col2:
        st.success("✅ DEV tools unlocked")
else:
    st.info("DEV tools locked (enter code to unlock).")

st.divider()

st.subheader("Seller (your company) — typed once for all PDFs")
seller_name = st.text_input("Seller Name", value="My Company")
seller_siret = st.text_input("Seller SIRET", value="12345678900011")
seller_vat = st.text_input("Seller VAT (FR...)", value="FR11123456789")

st.subheader("Defaults (used if OCR misses something)")
default_buyer_name = st.text_input("Default Buyer Name", value="Customer")
default_vat_rate = st.text_input("Default VAT rate % (used only if we cannot compute)", value="20")

uploaded_pdfs = st.file_uploader(
    "Upload invoice PDFs (you can select many)",
    type=["pdf"],
    accept_multiple_files=True
)

st.divider()

if not uploaded_pdfs:
    st.info("Upload PDFs to enable bulk conversion.")
    st.stop()

# ---- Free plan limit (monthly) ----
usage = load_usage()
month_key = current_month_key()
used_this_month = get_month_count(usage, month_key)

if pro_mode:
    st.success("⭐ PRO mode is ON → Unlimited conversions.")
else:
    st.info(f"🧾 Free plan usage: {used_this_month}/{FREE_LIMIT_PER_MONTH} PDFs used this month ({month_key})")

    remaining = FREE_LIMIT_PER_MONTH - used_this_month
    if remaining <= 0:
        st.error("❌ Free limit reached for this month. (In real SaaS: ask user to upgrade.)")
        st.stop()

    if len(uploaded_pdfs) > remaining:
        st.error(f"❌ You uploaded {len(uploaded_pdfs)} PDFs, but only {remaining} free PDFs remaining this month.")
        st.stop()

st.write(f"📄 PDFs selected: **{len(uploaded_pdfs)}**")

if st.button("Convert ALL to Factur-X (ZIP)"):
    out_root = Path("output")
    out_root.mkdir(exist_ok=True)
    batch_folder = out_root / f"bulk_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    batch_folder.mkdir(exist_ok=True)

    results = []
    zip_buffer = io.BytesIO()

    progress = st.progress(0)
    status = st.empty()

    default_vat_rate_dec = to_decimal(default_vat_rate)

    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i, up in enumerate(uploaded_pdfs, start=1):
            status.write(f"⏳ Processing {i}/{len(uploaded_pdfs)}: **{up.name}**")
            progress.progress(int((i - 1) / len(uploaded_pdfs) * 100))

            try:
                pdf_bytes = up.read()

                # 1) Extract fields
                if use_azure:
                    if not azure_confirm:
                        raise Exception("Azure OCR is ON, but you did not confirm the cost checkbox.")
                    fields = azure_extract_invoice_fields(pdf_bytes)
                    ocr_used = "azure"
                else:
                    fields = extract_fields_text(pdf_bytes)
                    ocr_used = "text"

                # 2) Build per-invoice values (with fallbacks)
                inv_no = fields.get("invoice_number") or Path(up.name).stem
                inv_no = safe_name(inv_no)

                inv_date = fields.get("invoice_date") or date.today()
                buyer_name = (fields.get("buyer_name") or default_buyer_name or "Customer").strip()

                total_ht = to_decimal(fields.get("total_ht_str"))
                total_ttc = to_decimal(fields.get("total_ttc_str"))

                vat_rate = None
                if total_ht is not None and total_ttc is not None:
                    vat_rate = compute_vat_rate_percent(total_ht, total_ttc)

                if vat_rate is None:
                    vat_rate = default_vat_rate_dec

                if total_ht is None:
                    raise Exception("Missing Total HT (SubTotal). OCR could not find it.")
                if vat_rate is None:
                    raise Exception("Missing VAT rate. OCR could not compute it and default VAT rate is invalid.")

                # 3) Build XML
                build_args = dict(
                    invoice_number=inv_no,
                    invoice_date=inv_date,
                    seller_name=seller_name,
                    seller_siret=seller_siret,
                    seller_vat=seller_vat,
                    buyer_name=buyer_name,
                    total_ht=total_ht,
                    vat_rate_percent=vat_rate,
                )

                xml_bytes = build_facturx_minimum_xml(**build_args)

                # 4) Validate XML
                validate_facturx_minimum(xml_bytes)

                # 5) Embed into PDF
                out_pdf_bytes = embed_facturx(pdf_bytes, xml_bytes)

                # 6) Save locally
                xml_path = batch_folder / f"{inv_no}_facturx.xml"
                pdf_path = batch_folder / f"{inv_no}_facturx.pdf"
                report_path = batch_folder / f"{inv_no}_report.txt"

                xml_path.write_bytes(xml_bytes)
                pdf_path.write_bytes(out_pdf_bytes)

                report_text = f"""FACTUR-X BULK REPORT
-------------------
SourceFile: {up.name}
OCR Used: {ocr_used}

InvoiceNumber: {inv_no}
InvoiceDate: {inv_date}

SellerName: {seller_name}
SellerSIRET: {seller_siret}
SellerVAT: {seller_vat}

BuyerName: {buyer_name}

TotalHT: {total_ht}
VATRatePercent: {vat_rate}

XML Validated: True
XML File: {xml_path}
PDF File: {pdf_path}
GeneratedAt: {datetime.now().isoformat()}
"""
                report_path.write_text(report_text, encoding="utf-8")

                # 7) Add to ZIP
                zf.writestr(f"{inv_no}/{inv_no}_facturx.xml", xml_bytes)
                zf.writestr(f"{inv_no}/{inv_no}_facturx.pdf", out_pdf_bytes)
                zf.writestr(f"{inv_no}/{inv_no}_report.txt", report_text)

                results.append(f"✅ {up.name} → OK ({inv_no})")

                # ✅ Count only successful conversions (FREE mode only)
                if not pro_mode:
                    increment_month_count(usage, month_key, 1)
                    save_usage(usage)

            except Exception as e:
                results.append(f"❌ {up.name} → FAILED: {str(e)}")

        summary_text = "BULK SUMMARY\n-----------\n" + "\n".join(results) + "\n"
        zf.writestr("bulk_summary.txt", summary_text)

    progress.progress(100)
    status.write("✅ Bulk conversion finished.")

    st.subheader("Results")
    st.code("\n".join(results))

    st.info(f"📁 Saved batch folder locally: {batch_folder}")

    zip_buffer.seek(0)
    st.download_button(
        "Download ZIP (all PDFs + XML + reports)",
        data=zip_buffer.getvalue(),
        file_name=f"{batch_folder.name}.zip",
        mime="application/zip",
    )
