import io
import zipfile
import os
import re
import pandas as pd
from datetime import date, datetime
from decimal import Decimal
import streamlit as st

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from pdf_autofill import extract_fields_text, azure_extract_invoice_fields
from facturx_engine import embed_facturx
from facturx_xml import build_facturx_minimum_xml
from validator import validate_facturx_minimum

# ============================================================
# 1. PAGE CONFIG & STYLING
# ============================================================
st.set_page_config(page_title="Factur-X SaaS", layout="centered")
st.markdown("""
    <style>
    .metric-card { background-color: #f0f2f6; padding: 15px; border-radius: 10px; border-left: 5px solid #28a745; }
    </style>
""", unsafe_allow_html=True)

# ============================================================
# 2. CONFIGURATION
# ============================================================
AZURE_ENDPOINT = None
AZURE_KEY = None

try:
    if "DOCUMENTINTELLIGENCE_ENDPOINT" in st.secrets:
        AZURE_ENDPOINT = st.secrets["DOCUMENTINTELLIGENCE_ENDPOINT"]
    if "DOCUMENTINTELLIGENCE_API_KEY" in st.secrets:
        AZURE_KEY = st.secrets["DOCUMENTINTELLIGENCE_API_KEY"]
except Exception:
    pass

if not AZURE_ENDPOINT:
    AZURE_ENDPOINT = os.getenv("DOCUMENTINTELLIGENCE_ENDPOINT")
if not AZURE_KEY:
    AZURE_KEY = os.getenv("DOCUMENTINTELLIGENCE_API_KEY")

# ============================================================
# 3. SESSION STATE
# ============================================================
if "user_data" not in st.session_state:
    st.session_state.user_data = None 

if "ocr_data" not in st.session_state:
    st.session_state.ocr_data = {}
if "last_pdf" not in st.session_state:
    st.session_state.last_pdf = None

if "bulk_zip" not in st.session_state:
    st.session_state.bulk_zip = None

# ============================================================
# 4. LOGIN SCREEN
# ============================================================
def login_screen():
    st.title("🔐 Login to Factur-X Pro")
    st.markdown("Enter your business details to start.")
    
    with st.form("login_form"):
        email = st.text_input("Email Address")
        siret = st.text_input("Your Company SIRET (Required)", value="80258593400018")
        vat = st.text_input("Your VAT Number", value="FR34802585934")
        
        submitted = st.form_submit_button("Access Dashboard")
        
        if submitted:
            if email and siret and vat:
                st.session_state.user_data = {
                    "email": email,
                    "siret": siret,
                    "vat": vat,
                    "quota_limit": 5,
                    "quota_used": 0
                }
                st.rerun()
            else:
                st.error("Please fill in all fields.")

# ============================================================
# 5. MODE A: SINGLE STUDIO
# ============================================================
def render_single_mode(user):
    st.subheader("Single Invoice Studio")
    st.caption("Upload, Edit, and Certify one invoice at a time.")
    
    uploaded_pdf = st.file_uploader("Drop invoice PDF here", type=["pdf"], key="single_uploader")

    if uploaded_pdf and uploaded_pdf.name != st.session_state.last_pdf:
        st.session_state.ocr_data = {}
        st.session_state.last_pdf = uploaded_pdf.name

    col_act1, col_act2 = st.columns(2)
    
    if col_act1.button("⚡ Quick Scan (Text)", key="btn_text"):
        if uploaded_pdf:
            st.session_state.ocr_data = extract_fields_text(uploaded_pdf.getvalue())
            st.success("Scan complete.")
        else: st.warning("Upload first.")

    if col_act2.button("🧠 AI Deep Scan", key="btn_ai"):
        if not uploaded_pdf: st.warning("Upload first.")
        elif user['quota_used'] >= user['quota_limit']: st.error("Quota exceeded.")
        elif not AZURE_ENDPOINT or not AZURE_KEY: st.error("System Error: AI Keys missing.")
        else:
            with st.spinner("AI analyzing..."):
                st.session_state.user_data['quota_used'] += 1
                data = azure_extract_invoice_fields(uploaded_pdf.getvalue(), AZURE_ENDPOINT, AZURE_KEY)
                st.session_state.ocr_data = data
                st.success("Analysis complete.")
                st.rerun()

    if st.session_state.ocr_data or uploaded_pdf:
        st.divider()
        data = st.session_state.ocr_data
        
        c1, c2, c3 = st.columns(3)
        invoice_number = c1.text_input("Invoice #", value=str(data.get("invoice_number", "")))
        invoice_date = c2.date_input("Date", value=data.get("invoice_date") or date.today())
        currency = c3.selectbox("Currency", ["EUR", "USD"], index=0)
        
        f1, f2, f3 = st.columns(3)
        raw_ht = Decimal(str(data.get("total_ht_str", "0")).replace(",", ".") or "0")
        raw_ttc = Decimal(str(data.get("total_ttc_str", "0")).replace(",", ".") or "0")
        
        default_rate = "20.00"
        if raw_ht > 0 and raw_ttc > raw_ht:
            rate_val = ((raw_ttc - raw_ht) / raw_ht * 100).quantize(Decimal("0.01"))
            default_rate = str(rate_val)
        
        total_ht_str = f1.text_input("Net Amount (HT)", value=str(data.get("total_ht_str", "0.00")))
        vat_rate_str = f2.text_input("VAT Rate (%)", value=default_rate)
        
        try:
            ht_val = Decimal(total_ht_str.replace(",", ".") or "0")
            rate_val = Decimal(vat_rate_str.replace(",", ".") or "0")
            tax_val = (ht_val * rate_val / 100).quantize(Decimal("0.01"))
            ttc_val = ht_val + tax_val
        except:
            tax_val = Decimal("0")
            ttc_val = Decimal("0")
            
        f3.metric("Total (TTC)", f"{ttc_val} €", delta=f"Tax: {tax_val} €")

        p1, p2 = st.columns(2)
        seller_name = p1.text_input("Seller Name", value=str(data.get("seller_name", "")))
        buyer_name = p2.text_input("Buyer Name", value=str(data.get("buyer_name", "")))

        st.divider()
        if st.button("✨ Generate Compliant Bundle", type="primary"):
            try:
                xml = build_facturx_minimum_xml(
                    invoice_number=invoice_number,
                    invoice_date=invoice_date,
                    seller_name=seller_name,
                    seller_siret=user['siret'],
                    seller_vat=user['vat'],
                    buyer_name=buyer_name,
                    total_ht=ht_val,
                    vat_rate_percent=rate_val,
                )
                
                validate_facturx_minimum(xml)
                out_pdf = embed_facturx(uploaded_pdf.getvalue(), xml)
                
                audit_data = {
                    "Field": ["Compliance Profile", "Invoice Number", "Date", "Seller", "Buyer", "Net Amount", "Tax Rate", "Total TTC"],
                    "Value": ["Factur-X Minimum", invoice_number, invoice_date, seller_name, buyer_name, str(ht_val), str(rate_val)+"%", str(ttc_val)],
                }
                df_audit = pd.DataFrame(audit_data)
                
                zip_buf = io.BytesIO()
                excel_buf = io.BytesIO()
                with pd.ExcelWriter(excel_buf, engine='openpyxl') as writer:
                    df_audit.to_excel(writer, index=False, sheet_name="Summary")
                
                safe_name = re.sub(r'[\\/*?:"<>|]', "_", invoice_number)
                
                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as z:
                    z.writestr(f"{safe_name}_facturx.pdf", out_pdf)
                    z.writestr("audit_report.xlsx", excel_buf.getvalue())
                    
                st.success("✅ Certified Bundle Generated")
                st.download_button("Download ZIP", zip_buf.getvalue(), f"{safe_name}_bundle.zip")
                
            except Exception as e:
                st.error(f"Error: {e}")

# ============================================================
# 6. MODE B: BULK PROCESSOR
# ============================================================
def render_bulk_mode(user):
    st.subheader("Batch Processor (Bulk)")
    st.info("⚠️ Files with missing data will be skipped and flagged in the report.")
    
    files = st.file_uploader("Upload multiple PDFs", type=["pdf"], accept_multiple_files=True)
    
    if st.session_state.bulk_zip:
        st.success("✅ Batch Processing Complete!")
        st.download_button(
            "Download Processed Batch (ZIP)", 
            st.session_state.bulk_zip, 
            "batch_output.zip",
            type="primary"
        )
        if st.button("Start New Batch"):
            st.session_state.bulk_zip = None
            st.rerun()
    
    if files and not st.session_state.bulk_zip:
        remaining = user['quota_limit'] - user['quota_used']
        count = len(files)
        st.write(f"Selected **{count}** files.")
        
        if count > remaining:
            st.error(f"❌ You selected {count} files, but only have {remaining} credits left.")
            return

        if st.button("🚀 Process All Files", type="primary"):
            if not AZURE_ENDPOINT or not AZURE_KEY:
                st.error("AI Keys missing.")
                return

            progress_bar = st.progress(0)
            status_text = st.empty()
            
            master_zip = io.BytesIO()
            report_rows = []
            
            with zipfile.ZipFile(master_zip, "w", zipfile.ZIP_DEFLATED) as z:
                
                for i, pdf_file in enumerate(files):
                    status_text.write(f"Processing {pdf_file.name}...")
                    st.session_state.user_data['quota_used'] += 1
                    
                    try:
                        data = azure_extract_invoice_fields(pdf_file.getvalue(), AZURE_ENDPOINT, AZURE_KEY)
                        
                        if not data.get("invoice_number") or not data.get("total_ht_str"):
                            report_rows.append({
                                "File": pdf_file.name, 
                                "Status": "FAILED", 
                                "Compliance Profile": "N/A",
                                "Reason": "Missing Invoice# or Total"
                            })
                            continue 
                        
                        ht_val = Decimal(data["total_ht_str"].replace(",", "."))
                        rate_val = Decimal("20.00") 
                        
                        xml = build_facturx_minimum_xml(
                            invoice_number=data["invoice_number"],
                            invoice_date=data.get("invoice_date") or date.today(),
                            seller_name=data.get("seller_name", "Unknown"),
                            seller_siret=user['siret'],
                            seller_vat=user['vat'],
                            buyer_name=data.get("buyer_name", "Unknown"),
                            total_ht=ht_val,
                            vat_rate_percent=rate_val,
                        )
                        
                        out_pdf = embed_facturx(pdf_file.getvalue(), xml)
                        
                        safe_inv_num = re.sub(r'[\\/*?:"<>|]', "_", data["invoice_number"])
                        z.writestr(f"{safe_inv_num}_facturx.pdf", out_pdf)
                        
                        report_rows.append({
                            "File": pdf_file.name, 
                            "Status": "SUCCESS",
                            "Compliance Profile": "Factur-X Minimum",
                            "Invoice #": data["invoice_number"], 
                            "Total HT": str(ht_val)
                        })
                        
                    except Exception as e:
                        report_rows.append({"File": pdf_file.name, "Status": "ERROR", "Reason": str(e)})
                    
                    progress_bar.progress((i + 1) / count)
                
                df_report = pd.DataFrame(report_rows)
                excel_buf = io.BytesIO()
                with pd.ExcelWriter(excel_buf, engine='openpyxl') as writer:
                    df_report.to_excel(writer, index=False)
                z.writestr("Master_Processing_Report.xlsx", excel_buf.getvalue())

            st.session_state.bulk_zip = master_zip.getvalue()
            st.rerun()

# ============================================================
# 7. MAIN DASHBOARD ROUTER
# ============================================================
def main_dashboard():
    user = st.session_state.user_data
    
    col_head1, col_head2 = st.columns([2, 1])
    with col_head1:
        st.title("Factur-X Studio")
        # --- FIXED HEADER ---
        st.caption(f"🏢 **SIRET:** {user['siret']}  |  🆔 **VAT:** {user['vat']}")
    
    with col_head2:
        remaining = user['quota_limit'] - user['quota_used']
        st.metric("Free Quota", f"{remaining} Left")
        if remaining == 0: st.error("Limit Reached")

    st.divider()
    mode = st.radio("Select Mode:", ["Single Invoice Studio", "Batch Processor (Bulk)"], horizontal=True)
    
    if mode == "Single Invoice Studio":
        st.session_state.bulk_zip = None
        render_single_mode(user)
    else:
        render_bulk_mode(user)

    with st.expander("🛠 Developer Tools"):
        if st.button("Reset Quota"):
            st.session_state.user_data['quota_used'] = 0
            st.rerun()

# ============================================================
# 8. APP ENTRY POINT
# ============================================================
if st.session_state.user_data is None:
    login_screen()
else:
    main_dashboard()