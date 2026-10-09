import io
from datetime import date
from typing import Union
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from app.core.logging import logger


def generate_certificate_pdf(
    recipient_name: str,
    event_name: str,
    issue_date: Union[date, str],
    certificate_id: str
) -> bytes:
    """
    Renders a high-resolution, professional PDF certificate using ReportLab.
    Includes dynamic font scaling for long names and events, geometric borders,
    and security/audit metadata.
    """
    buffer = io.BytesIO()
    width, height = landscape(A4)  # ~841.89 x 595.27 points

    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    c.setTitle(f"Certificate - {recipient_name}")
    c.setAuthor("Bulk Certificate Generator")
    c.setSubject(event_name)

    # 1. Background & Margins
    # Outer dark border
    c.setStrokeColor(colors.HexColor("#0F172A"))  # Slate-900
    c.setLineWidth(6)
    c.rect(20, 20, width - 40, height - 40)

    # Inner ornate gold border
    c.setStrokeColor(colors.HexColor("#D97706"))  # Amber-600
    c.setLineWidth(2)
    c.rect(28, 28, width - 56, height - 56)

    # Thin innermost accent border
    c.setStrokeColor(colors.HexColor("#CBD5E1"))  # Slate-300
    c.setLineWidth(0.75)
    c.rect(34, 34, width - 68, height - 68)

    # Corner decorative geometric elements
    corner_size = 35
    c.setFillColor(colors.HexColor("#1E3A8A"))  # Dark Blue
    # Top-Left corner accent
    p = c.beginPath()
    p.moveTo(28, height - 28)
    p.lineTo(28 + corner_size, height - 28)
    p.lineTo(28, height - 28 - corner_size)
    p.close()
    c.drawPath(p, fill=1, stroke=0)

    # Top-Right corner accent
    p = c.beginPath()
    p.moveTo(width - 28, height - 28)
    p.lineTo(width - 28 - corner_size, height - 28)
    p.lineTo(width - 28, height - 28 - corner_size)
    p.close()
    c.drawPath(p, fill=1, stroke=0)

    # Bottom-Left corner accent
    p = c.beginPath()
    p.moveTo(28, 28)
    p.lineTo(28 + corner_size, 28)
    p.lineTo(28, 28 + corner_size)
    p.close()
    c.drawPath(p, fill=1, stroke=0)

    # Bottom-Right corner accent
    p = c.beginPath()
    p.moveTo(width - 28, 28)
    p.lineTo(width - 28 - corner_size, 28)
    p.lineTo(width - 28, 28 + corner_size)
    p.close()
    c.drawPath(p, fill=1, stroke=0)

    # 2. Header & Branding
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.HexColor("#D97706"))
    c.drawCentredString(width / 2.0, height - 75, "OFFICIAL CERTIFICATE OF COMPLETION")

    c.setFont("Times-Bold", 34)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.drawCentredString(width / 2.0, height - 120, "CERTIFICATE OF EXCELLENCE")

    c.setStrokeColor(colors.HexColor("#D97706"))
    c.setLineWidth(1.5)
    c.line(width / 2.0 - 120, height - 132, width / 2.0 + 120, height - 132)

    # 3. Presentation Subtitle
    c.setFont("Helvetica", 14)
    c.setFillColor(colors.HexColor("#475569"))
    c.drawCentredString(width / 2.0, height - 165, "PROUDLY PRESENTED TO")

    # 4. Recipient Name with dynamic font scaling and clipping protection
    max_name_width = width - 160  # Printable text area
    name_font_size = 36
    font_name = "Times-BoldItalic"
    c.setFont(font_name, name_font_size)
    display_name = recipient_name
    
    current_name_width = c.stringWidth(display_name, font_name, name_font_size)
    while current_name_width > max_name_width and name_font_size > 12:
        name_font_size -= 2
        c.setFont(font_name, name_font_size)
        current_name_width = c.stringWidth(display_name, font_name, name_font_size)

    # If still exceeding printable width at minimum font size, gracefully truncate with ellipsis
    while current_name_width > max_name_width and len(display_name) > 4:
        display_name = display_name[:-4] + "..."
        current_name_width = c.stringWidth(display_name, font_name, name_font_size)

    c.setFillColor(colors.HexColor("#1E293B"))
    c.drawCentredString(width / 2.0, height - 225, display_name)

    # Elegant decorative line under recipient name
    name_line_w = min(current_name_width + 40, max_name_width)
    c.setStrokeColor(colors.HexColor("#94A3B8"))
    c.setLineWidth(1)
    c.line((width - name_line_w) / 2.0, height - 235, (width + name_line_w) / 2.0, height - 235)

    # 5. Event and Recognition Text
    c.setFont("Helvetica", 14)
    c.setFillColor(colors.HexColor("#475569"))
    c.drawCentredString(width / 2.0, height - 275, "in recognition of successful completion and outstanding performance in")

    # Event Name with dynamic font scaling and clipping protection
    event_font_size = 24
    event_font_name = "Helvetica-Bold"
    c.setFont(event_font_name, event_font_size)
    display_event = event_name
    event_width = c.stringWidth(display_event, event_font_name, event_font_size)
    while event_width > max_name_width and event_font_size > 10:
        event_font_size -= 2
        c.setFont(event_font_name, event_font_size)
        event_width = c.stringWidth(display_event, event_font_name, event_font_size)

    # If still exceeding printable width at minimum font size, gracefully truncate with ellipsis
    while event_width > max_name_width and len(display_event) > 4:
        display_event = display_event[:-4] + "..."
        event_width = c.stringWidth(display_event, event_font_name, event_font_size)

    c.setFillColor(colors.HexColor("#0F172A"))
    c.drawCentredString(width / 2.0, height - 320, display_event)

    # 6. Date Formatting
    if isinstance(issue_date, date):
        formatted_date = issue_date.strftime("%B %d, %Y")
    else:
        try:
            parsed_d = date.fromisoformat(str(issue_date))
            formatted_date = parsed_d.strftime("%B %d, %Y")
        except (ValueError, TypeError):
            formatted_date = str(issue_date)

    # 7. Verification Seal (Center Medallion)
    seal_x = width / 2.0
    seal_y = 120
    c.setStrokeColor(colors.HexColor("#D97706"))
    c.setFillColor(colors.HexColor("#FEF3C7"))
    c.circle(seal_x, seal_y, 32, fill=1, stroke=1)
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#92400E"))
    c.drawCentredString(seal_x, seal_y + 8, "VERIFIED")
    c.drawCentredString(seal_x, seal_y - 4, "DIGITAL")
    c.drawCentredString(seal_x, seal_y - 16, "CREDENTIAL")

    # 8. Footer Columns
    # Left Column: Issue Date
    date_x = 120
    c.setStrokeColor(colors.HexColor("#94A3B8"))
    c.setLineWidth(1)
    c.line(date_x - 50, 110, date_x + 90, 110)
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.drawCentredString(date_x + 20, 120, formatted_date)
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawCentredString(date_x + 20, 95, "Date of Issuance")

    # Right Column: Signatory
    sig_x = width - 140
    c.line(sig_x - 70, 110, sig_x + 70, 110)
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.drawCentredString(sig_x, 120, "Authorized Signatory")
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawCentredString(sig_x, 95, "Program Director")

    # 9. Audit & Security Identification Header/Footer
    c.setFont("Courier", 9)
    c.setFillColor(colors.HexColor("#94A3B8"))
    c.drawCentredString(width / 2.0, 48, f"Certificate ID: {certificate_id}  |  Authenticity guaranteed via Digital Ledger")

    c.showPage()
    c.save()

    buffer.seek(0)
    pdf_bytes = buffer.getvalue()
    logger.debug("Generated certificate PDF for %s (%d bytes)", recipient_name, len(pdf_bytes))
    return pdf_bytes
