import io
import html

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


def create_filters_pdf(filters):
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "FilterTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=18,
    )

    body_style = ParagraphStyle(
        "FilterBody",
        parent=styles["BodyText"],
        fontSize=9,
        leading=13,
        wordWrap="CJK",
    )

    story = [
        Paragraph("Available Filters Report", title_style),
        Spacer(1, 12),
        Paragraph(
            f"Total Filters: <b>{len(filters)}</b>",
            body_style,
        ),
        Spacer(1, 15),
    ]

    rows = [["No.", "Filter Keyword", "Buttons Count"]]

    for index, item in enumerate(filters, start=1):
        keyword = html.escape(str(item.get("keyword", "")))
        buttons = item.get("buttons", []) or []

        rows.append([
            str(index),
            Paragraph(keyword or "(empty)", body_style),
            str(len(buttons)),
        ])

    if filters:
        table = Table(
            rows,
            colWidths=[40, 330, 100],
            repeatRows=1,
        )

        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#263238")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))

        story.append(table)
    else:
        story.append(
            Paragraph("No filters found.", body_style)
        )

    doc.build(story)
    buffer.seek(0)

    return buffer.getvalue()
