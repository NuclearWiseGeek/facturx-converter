from datetime import date
from decimal import Decimal
import textwrap

def format_date(d):
    """Format date to YYYYMMDD string."""
    if isinstance(d, str):
        return d.replace("-", "")
    return d.strftime("%Y%m%d")

def build_facturx_basic_xml(
    invoice_number,
    invoice_date,
    seller_name,
    seller_siret,
    seller_vat,
    buyer_name,
    line_items,  # NEW: List of dictionaries [{'name': '...', 'qty': 1, 'price': 10.0}]
    vat_rate_percent=Decimal("20.0")
):
    """
    Generates Factur-X BASIC profile XML (includes Line Items).
    """
    
    # 1. CALCULATE TOTALS FROM LINES
    # If no lines provided, create a dummy one (fallback)
    if not line_items:
        line_items = [{
            "name": "Services",
            "quantity": Decimal("1.0"),
            "unit_price": Decimal("0.0") # Will be filled later or handled by caller
        }]

    total_net = Decimal("0.00")
    total_tax = Decimal("0.00")
    
    # Pre-calculate totals to ensure header matches lines
    processed_lines = []
    for idx, item in enumerate(line_items):
        qty = Decimal(str(item.get("quantity", "1.0")))
        price = Decimal(str(item.get("unit_price", "0.0")))
        net = qty * price
        tax = net * (vat_rate_percent / 100)
        
        processed_lines.append({
            "id": str(idx + 1),
            "name": item.get("name", "Item"),
            "qty": qty,
            "price": price,
            "net": net
        })
        total_net += net
        total_tax += tax
        
    total_ttc = total_net + total_tax
    
    # 2. DEFINE XML TEMPLATE (BASIC PROFILE)
    # Note: GuidelineID is now 'urn:cen.eu:en16931:2017#compliant#urn:factur-x.eu:1p0:basic'
    xml_template = f"""<?xml version='1.0' encoding='UTF-8'?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100" 
xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100" 
xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
    <rsm:ExchangedDocumentContext>
        <ram:GuidelineSpecifiedDocumentContextParameter>
            <ram:ID>urn:cen.eu:en16931:2017#compliant#urn:factur-x.eu:1p0:basic</ram:ID>
        </ram:GuidelineSpecifiedDocumentContextParameter>
    </rsm:ExchangedDocumentContext>
    <rsm:ExchangedDocument>
        <ram:ID>{invoice_number}</ram:ID>
        <ram:TypeCode>380</ram:TypeCode>
        <ram:IssueDateTime>
            <udt:DateTimeString format="102">{format_date(invoice_date)}</udt:DateTimeString>
        </ram:IssueDateTime>
    </rsm:ExchangedDocument>
    <rsm:SupplyChainTradeTransaction>
        
        {{line_items_xml}}
        <ram:ApplicableHeaderTradeAgreement>
            <ram:SellerTradeParty>
                <ram:Name>{seller_name}</ram:Name>
                <ram:SpecifiedLegalOrganization>
                   <ram:ID schemeID="0002">{seller_siret}</ram:ID>
                </ram:SpecifiedLegalOrganization>
                <ram:SpecifiedTaxRegistration>
                    <ram:ID schemeID="VA">{seller_vat}</ram:ID>
                </ram:SpecifiedTaxRegistration>
            </ram:SellerTradeParty>
            <ram:BuyerTradeParty>
                <ram:Name>{buyer_name}</ram:Name>
            </ram:BuyerTradeParty>
        </ram:ApplicableHeaderTradeAgreement>

        <ram:ApplicableHeaderTradeDelivery>
        </ram:ApplicableHeaderTradeDelivery>

        <ram:ApplicableHeaderTradeSettlement>
            <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
            <ram:ApplicableTradeTax>
                <ram:CalculatedAmount>{total_tax:.2f}</ram:CalculatedAmount>
                <ram:TypeCode>VAT</ram:TypeCode>
                <ram:BasisAmount>{total_net:.2f}</ram:BasisAmount>
                <ram:CategoryCode>S</ram:CategoryCode>
                <ram:RateApplicablePercent>{vat_rate_percent:.2f}</ram:RateApplicablePercent>
            </ram:ApplicableTradeTax>
            <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
                <ram:LineTotalAmount>{total_net:.2f}</ram:LineTotalAmount>
                <ram:TaxBasisTotalAmount>{total_net:.2f}</ram:TaxBasisTotalAmount>
                <ram:TaxTotalAmount currencyID="EUR">{total_tax:.2f}</ram:TaxTotalAmount>
                <ram:GrandTotalAmount>{total_ttc:.2f}</ram:GrandTotalAmount>
                <ram:DuePayableAmount>{total_ttc:.2f}</ram:DuePayableAmount>
            </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
        </ram:ApplicableHeaderTradeSettlement>
    </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>"""

    # 3. BUILD LINE ITEMS XML
    lines_xml_block = ""
    for line in processed_lines:
        lines_xml_block += f"""
        <ram:IncludedSupplyChainTradeLineItem>
            <ram:AssociatedDocumentLineDocument>
                <ram:LineID>{line['id']}</ram:LineID>
            </ram:AssociatedDocumentLineDocument>
            <ram:SpecifiedTradeProduct>
                <ram:Name>{line['name']}</ram:Name>
            </ram:SpecifiedTradeProduct>
            <ram:SpecifiedLineTradeAgreement>
                <ram:NetPriceProductTradePrice>
                    <ram:ChargeAmount>{line['price']:.2f}</ram:ChargeAmount>
                </ram:NetPriceProductTradePrice>
            </ram:SpecifiedLineTradeAgreement>
            <ram:SpecifiedLineTradeDelivery>
                <ram:BilledQuantity unitCode="C62">{line['qty']:.2f}</ram:BilledQuantity>
            </ram:SpecifiedLineTradeDelivery>
            <ram:SpecifiedLineTradeSettlement>
                <ram:ApplicableTradeTax>
                    <ram:TypeCode>VAT</ram:TypeCode>
                    <ram:CategoryCode>S</ram:CategoryCode>
                    <ram:RateApplicablePercent>{vat_rate_percent:.2f}</ram:RateApplicablePercent>
                </ram:ApplicableTradeTax>
                <ram:SpecifiedTradeSettlementLineMonetarySummation>
                    <ram:LineTotalAmount>{line['net']:.2f}</ram:LineTotalAmount>
                </ram:SpecifiedTradeSettlementLineMonetarySummation>
            </ram:SpecifiedLineTradeSettlement>
        </ram:IncludedSupplyChainTradeLineItem>"""

    return xml_template.replace("{line_items_xml}", lines_xml_block)