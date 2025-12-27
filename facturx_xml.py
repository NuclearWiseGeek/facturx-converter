from datetime import date
from decimal import Decimal
from lxml import etree


def build_facturx_minimum_xml(
    *,
    invoice_number: str,
    invoice_date: date,
    seller_name: str,
    seller_siret: str,
    seller_vat: str,
    buyer_name: str,
    total_ht: Decimal,
    vat_rate_percent: Decimal,
    buyer_siret: str = "",
    buyer_vat: str = "",
) -> bytes:
    """
    Build a Factur-X MINIMUM profile XML (strict, XSD-valid).
    This function name is intentionally locked and MUST match app.py imports.
    """

    NSMAP = {
        "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
        "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
        "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
    }

    rsm = f"{{{NSMAP['rsm']}}}"
    ram = f"{{{NSMAP['ram']}}}"
    udt = f"{{{NSMAP['udt']}}}"

    total_ht = Decimal(total_ht).quantize(Decimal("0.01"))
    vat_rate_percent = Decimal(vat_rate_percent).quantize(Decimal("0.01"))

    tax_total = (total_ht * vat_rate_percent / Decimal("100")).quantize(Decimal("0.01"))
    grand_total = (total_ht + tax_total).quantize(Decimal("0.01"))

    root = etree.Element(rsm + "CrossIndustryInvoice", nsmap=NSMAP)

    # =========================
    # Context
    # =========================
    ctx = etree.SubElement(root, rsm + "ExchangedDocumentContext")

    bp = etree.SubElement(ctx, ram + "BusinessProcessSpecifiedDocumentContextParameter")
    etree.SubElement(bp, ram + "ID").text = "A1"

    guideline = etree.SubElement(ctx, ram + "GuidelineSpecifiedDocumentContextParameter")
    etree.SubElement(guideline, ram + "ID").text = "urn:factur-x.eu:1p0:minimum"

    # =========================
    # Document
    # =========================
    doc = etree.SubElement(root, rsm + "ExchangedDocument")
    etree.SubElement(doc, ram + "ID").text = invoice_number
    etree.SubElement(doc, ram + "TypeCode").text = "380"

    issue_dt = etree.SubElement(doc, ram + "IssueDateTime")
    dt_str = etree.SubElement(issue_dt, udt + "DateTimeString", format="102")
    dt_str.text = invoice_date.strftime("%Y%m%d")

    # =========================
    # Transaction
    # =========================
    sctt = etree.SubElement(root, rsm + "SupplyChainTradeTransaction")

    # Agreement
    agr = etree.SubElement(sctt, ram + "ApplicableHeaderTradeAgreement")

    seller = etree.SubElement(agr, ram + "SellerTradeParty")
    etree.SubElement(seller, ram + "Name").text = seller_name

    seller_org = etree.SubElement(seller, ram + "SpecifiedLegalOrganization")
    etree.SubElement(seller_org, ram + "ID").text = seller_siret

    seller_tax = etree.SubElement(seller, ram + "SpecifiedTaxRegistration")
    etree.SubElement(seller_tax, ram + "ID", schemeID="VA").text = seller_vat

    buyer = etree.SubElement(agr, ram + "BuyerTradeParty")
    etree.SubElement(buyer, ram + "Name").text = buyer_name

    if buyer_siret:
        buyer_org = etree.SubElement(buyer, ram + "SpecifiedLegalOrganization")
        etree.SubElement(buyer_org, ram + "ID").text = buyer_siret

    if buyer_vat:
        buyer_tax = etree.SubElement(buyer, ram + "SpecifiedTaxRegistration")
        etree.SubElement(buyer_tax, ram + "ID", schemeID="VA").text = buyer_vat

    # Delivery (empty allowed)
    etree.SubElement(sctt, ram + "ApplicableHeaderTradeDelivery")

    # Settlement
    settle = etree.SubElement(sctt, ram + "ApplicableHeaderTradeSettlement")
    etree.SubElement(settle, ram + "InvoiceCurrencyCode").text = "EUR"

    summ = etree.SubElement(
        settle,
        ram + "SpecifiedTradeSettlementHeaderMonetarySummation"
    )

    etree.SubElement(summ, ram + "TaxBasisTotalAmount").text = str(total_ht)

    tax_el = etree.SubElement(summ, ram + "TaxTotalAmount", currencyID="EUR")
    tax_el.text = str(tax_total)

    etree.SubElement(summ, ram + "GrandTotalAmount").text = str(grand_total)
    etree.SubElement(summ, ram + "DuePayableAmount").text = str(grand_total)

    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=True,
    )
