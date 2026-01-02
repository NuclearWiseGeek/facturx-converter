import tempfile
import subprocess
from pathlib import Path


def validate_facturx_minimum(xml_bytes: bytes) -> None:
    """
    Validate Factur-X MINIMUM XML using the official factur-x CLI tool.
    Raises Exception if validation fails.
    """

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        xml_path = tmp_dir / "facturx.xml"
        xml_path.write_bytes(xml_bytes)

        # Official Factur-X XML validator (installed with factur-x)
        cmd = ["facturx-xmlcheck", str(xml_path)]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            raise Exception(
                "facturx-xmlcheck not found. "
                "Ensure 'factur-x' is installed in your venv."
            )

        if result.returncode != 0:
            error_msg = (result.stdout or "") + "\n" + (result.stderr or "")
            raise Exception(
                error_msg.strip()
                or "Factur-X XML failed XSD validation."
            )
