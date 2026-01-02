from facturx_xml import build_facturx_basic_xml
from datetime import date
from decimal import Decimal

# Fake data (simulating what Azure AI would give us)
fake_lines = [
    {"name": "Web Design", "quantity": 10, "unit_price": 50},  # Should be 500
    {"name": "Hosting", "quantity": 1, "unit_price": 100}      # Should be 100
]

xml_output = build_facturx_basic_xml(
    "INV-TEST-001", date.today(), 
    "My Company", "SIRET123", "VAT123", 
    "Client Co", 
    fake_lines
)

print(xml_output)