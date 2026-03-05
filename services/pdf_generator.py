import matplotlib
matplotlib.use('Agg')  # Non-interactive backend — MUST be before pyplot import
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image
)
import os
import uuid

REPORTS_DIR = "static/reports"
os.makedirs(REPORTS_DIR, exist_ok=True)

# ── Colour palette ─────────────────────────────────────────────────────────────
RED            = colors.HexColor("#C0392B")
DARK_RED       = colors.HexColor("#922B21")
LIGHT_RED      = colors.HexColor("#FADBD8")
DARK_GRAY      = colors.HexColor("#2C3E50")
MID_GRAY       = colors.HexColor("#7F8C8D")
LIGHT_GRAY     = colors.HexColor("#F2F3F4")
WARNING_BG     = colors.HexColor("#FEF9E7")
WARNING_BORDER = colors.HexColor("#F39C12")
TABLE_HEADER   = colors.HexColor("#2C3E50")
TABLE_ALT      = colors.HexColor("#EBF5FB")


# ── ECG Plot (hospital-style) ──────────────────────────────────────────────────
def generate_ecg_plot(ecg_data, sample_rate=360):
    total_samples  = len(ecg_data)
    actual_duration = total_samples / sample_rate
    time_axis      = np.linspace(0, actual_duration, total_samples)

    fig, ax = plt.subplots(figsize=(14, 3.5))
    fig.patch.set_facecolor('#FFF5F5')
    ax.set_facecolor('#FFF5F5')

    # Minor grid: 1 mm squares (0.04 s x 0.1 mV)
    ax.set_xticks(np.arange(0, actual_duration + 0.04, 0.04), minor=True)
    ax.set_yticks(np.arange(-2, 2.1, 0.1), minor=True)
    ax.grid(which='minor', color='#F1948A', linewidth=0.3, alpha=0.6)

    # Major grid: 5 mm squares (0.2 s x 0.5 mV)
    ax.set_xticks(np.arange(0, actual_duration + 0.2, 0.2))
    ax.set_yticks(np.arange(-2, 2.1, 0.5))
    ax.grid(which='major', color='#E74C3C', linewidth=0.6, alpha=0.5)

    # ECG waveform
    ax.plot(time_axis, ecg_data, color='#1A1A1A', linewidth=0.9, zorder=5)

    # Standard 1mV calibration pulse at the start
    cal_x = [0, 0, 0.04, 0.04, 0.08]
    cal_y = [0, 1.0, 1.0, 0, 0]
    ax.plot(cal_x, cal_y, color='#1A1A1A', linewidth=1.2, zorder=6)
    ax.text(0.01, 1.05, '1mV', fontsize=6, color='#333333')

    ax.set_xlabel("Time (seconds)  —  25 mm/s", fontsize=8)
    ax.set_ylabel("Amplitude (mV)\n10 mm/mV",  fontsize=8)
    ax.set_title("Lead I — Rhythm Strip", fontsize=9,
                 fontweight='bold', color='#C0392B', pad=4)
    ax.set_xlim(0, actual_duration)
    ax.tick_params(labelsize=7)

    plt.tight_layout(pad=0.5)
    plot_path = f"{REPORTS_DIR}/ecg_{uuid.uuid4().hex}.png"
    plt.savefig(plot_path, dpi=180, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    plt.close()
    return plot_path


# ── Reusable helpers ───────────────────────────────────────────────────────────
def section_heading(text, styles):
    return Paragraph(text, ParagraphStyle(
        'SectionHeading',
        parent=styles['Normal'],
        fontSize=11,
        fontName='Helvetica-Bold',
        textColor=DARK_RED,
        spaceAfter=4,
        spaceBefore=10,
    ))


def info_table(rows, col_widths):
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('FONTNAME',       (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE',       (0, 0), (-1, -1), 9),
        ('FONTNAME',       (0, 0), (0, -1),  'Helvetica-Bold'),
        ('TEXTCOLOR',      (0, 0), (0, -1),  DARK_GRAY),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, TABLE_ALT]),
        ('GRID',           (0, 0), (-1, -1), 0.3, colors.HexColor("#D5D8DC")),
        ('LEFTPADDING',    (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',   (0, 0), (-1, -1), 6),
        ('TOPPADDING',     (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING',  (0, 0), (-1, -1), 4),
        ('VALIGN',         (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return t


# ── Main PDF generator ─────────────────────────────────────────────────────────
def generate_pdf(patient, prediction, ecg_data, sample_rate=250,model_name=None):
    """
    patient    : dict  — name, age, user_name, device_name
    prediction : dict  — condition, severity, confidence, heart_rate, rhythm_class
    ecg_data   : list  — raw float samples (last 30 s from React Native buffer)
    model_name : str   — name of the model used for prediction
    Returns (pdf_path, pdf_filename)
    """
    pdf_filename = f"ecg_report_{uuid.uuid4().hex}.pdf"
    pdf_path     = f"{REPORTS_DIR}/{pdf_filename}"

    doc = SimpleDocTemplate(
        pdf_path, pagesize=A4,
        rightMargin=15*mm, leftMargin=15*mm,
        topMargin=12*mm,   bottomMargin=15*mm,
    )

    styles = getSampleStyleSheet()
    W      = A4[0] - 30*mm      # usable page width
    now    = datetime.now()
    duration_seconds = len(ecg_data) / sample_rate

    small   = ParagraphStyle('small',  parent=styles['Normal'],
                             fontSize=8,   leading=11, textColor=MID_GRAY)
    normal  = ParagraphStyle('normal', parent=styles['Normal'],
                             fontSize=9,   leading=13)
    justify = ParagraphStyle('justify', parent=styles['Normal'],
                             fontSize=8.5, leading=13,
                             alignment=TA_JUSTIFY, textColor=DARK_GRAY)

    story = []

    # ── HEADER BANNER ──────────────────────────────────────────────────────────
    hdr_data = [[
        Paragraph(
            '<font color="#FFFFFF" size="16"><b>ECG REPORT</b></font><br/>'
            '<font color="#FADBD8" size="9">Automated Cardiac Rhythm Analysis</font>',
            ParagraphStyle('hL', alignment=TA_LEFT, leading=20)
        ),
        Paragraph(
            f'<font color="#FADBD8" size="8">'
            f'Generated: {now.strftime("%d %b %Y, %H:%M:%S")}<br/>'
            f'Report ID: {pdf_filename[:12].upper()}</font>',
            ParagraphStyle('hR', alignment=TA_LEFT, leading=13)
        )
    ]]
    hdr_tbl = Table(hdr_data, colWidths=[W * 0.6, W * 0.4])
    hdr_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), DARK_RED),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(hdr_tbl)
    story.append(Spacer(1, 6*mm))

    # ── ALERT BANNER ───────────────────────────────────────────────────────────
    condition    = prediction.get("condition",    "Unknown")
    severity     = prediction.get("severity",     "Unknown")
    confidence   = prediction.get("confidence",   0.0)
    heart_rate   = prediction.get("heart_rate",   "N/A")
    rhythm_class = prediction.get("rhythm_class", condition)

    alert_tbl = Table([[Paragraph(
        f'<font color="white"><b>ALERT: {condition.upper()}  |  '
        f'Severity: {severity}  |  '
        f'Confidence: {confidence * 100:.1f}%</b></font>',
        ParagraphStyle('al', fontSize=10, alignment=TA_CENTER, leading=16)
    )]], colWidths=[W])
    alert_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), RED),
        ('TOPPADDING',    (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
    ]))
    story.append(alert_tbl)
    story.append(Spacer(1, 5*mm))

    # ── PATIENT & DEVICE INFO (two-column) ─────────────────────────────────────
    story.append(section_heading("Patient &amp; Test Information", styles))

    col_w = (W - 6*mm) / 2
    patient_rows = [
        ["Patient Name",   patient.get("name",      "N/A")],
        ["Age",            str(patient.get("age",   "N/A"))],
        ["User / Profile", patient.get("user_name", "N/A")],
        ["Test Date",      now.strftime("%d %B %Y")],
        ["Test Time",      now.strftime("%H:%M:%S")],
    ]
    device_rows = [
        ["Device Name",        patient.get("device_name", "AD8232 + Ardunio UNO + ESP32")],
        ["Lead Configuration", "Single Lead (Lead I)"],
        ["Sample Rate",        f"{sample_rate} Hz"],
        ["Recording Duration", f"{int(duration_seconds)} seconds"],
        ["Processed By",       f"{model_name}"],
    ]

    two_col = Table(
        [[info_table(patient_rows, [38*mm, col_w - 38*mm]),
          info_table(device_rows,  [45*mm, col_w - 45*mm])]],
        colWidths=[col_w, col_w], hAlign='LEFT'
    )
    two_col.setStyle(TableStyle([
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3*mm),
        ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(two_col)
    story.append(Spacer(1, 4*mm))

    # ── HEART RATE & RHYTHM ────────────────────────────────────────────────────
    story.append(section_heading("Heart Rate &amp; Rhythm Data", styles))
    rhythm_rows = [
        ["Heart Rate",               f"{heart_rate} bpm"],
        ["Rhythm Classification",    rhythm_class],
        ["Detected Condition",       condition],
        ["Classification Confidence",f"{confidence * 100:.1f}%"],
        ["Beat Morphology",          "Single-lead analysis (Lead I only)"],
    ]
    story.append(info_table(rhythm_rows, [70*mm, W - 70*mm]))
    story.append(Spacer(1, 4*mm))

    # ── ECG WAVEFORM ───────────────────────────────────────────────────────────
    story.append(section_heading(
        "Heart Rhythm Graph — Lead I (30-Second Strip)", styles))
    story.append(Paragraph(
        "Standard paper speed: 25 mm/s &nbsp;|&nbsp; Amplitude: 10 mm/mV "
        "&nbsp;|&nbsp; Grid: 1 mm (minor) / 5 mm (major) &nbsp;|&nbsp; "
        "Calibration pulse shown at left",
        small
    ))
    story.append(Spacer(1, 2*mm))

    plot_path = generate_ecg_plot(ecg_data, sample_rate)
    story.append(Image(plot_path, width=W, height=55*mm))
    story.append(Spacer(1, 2*mm))

    # PQRST legend below the strip
    legend_tbl = Table([[
        Paragraph('<font color="#C0392B"><b>P wave</b></font>'
                  ' — Atrial depolarisation', small),
        Paragraph('<font color="#C0392B"><b>QRS complex</b></font>'
                  ' — Ventricular depolarisation', small),
        Paragraph('<font color="#C0392B"><b>T wave</b></font>'
                  ' — Ventricular repolarisation', small),
    ]], colWidths=[W/3, W/3, W/3])
    legend_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), LIGHT_GRAY),
        ('LEFTPADDING',   (0, 0), (-1, -1), 5),
        ('TOPPADDING',    (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('GRID',          (0, 0), (-1, -1), 0.3,
         colors.HexColor("#D5D8DC")),
    ]))
    story.append(legend_tbl)
    story.append(Spacer(1, 4*mm))

    # ── AUTOMATED RHYTHM CLASSIFICATION TABLE ──────────────────────────────────
    story.append(section_heading("Automated Rhythm Classification", styles))

    all_classes = [
        ("Normal Sinus Rhythm",          "N"),
        ("Arrhythmia",                   "A"),
        ("Supraventricular Ectopic Beat","S"),
        ("Fusion Beat",                  "F"),
        ("Unknown / Unclassifiable",     "Q"),
    ]
    class_rows = [["Class", "Symbol", "Result"]]
    for cls_name, symbol in all_classes:
        detected = (cls_name.lower() in condition.lower() or
                    symbol.lower() == rhythm_class.lower())
        class_rows.append([cls_name, symbol,
                           "DETECTED" if detected else "—"])

    class_tbl = Table(class_rows,
                      colWidths=[W * 0.55, W * 0.15, W * 0.30])
    class_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0),  TABLE_HEADER),
        ('TEXTCOLOR',     (0, 0), (-1, 0),  colors.white),
        ('FONTNAME',      (0, 0), (-1, 0),  'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, -1), 9),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, TABLE_ALT]),
        ('GRID',          (0, 0), (-1, -1), 0.3,
         colors.HexColor("#D5D8DC")),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ALIGN',         (1, 0), (2, -1),  'CENTER'),
        ('FONTNAME',      (2, 1), (2, -1),  'Helvetica-Bold'),
        ('TEXTCOLOR',     (2, 1), (2, -1),  RED),
    ]))
    story.append(class_tbl)
    story.append(Spacer(1, 4*mm))

    # ── PHYSICIAN REVIEW SPACE ─────────────────────────────────────────────────
    story.append(section_heading("Physician Review &amp; Summary", styles))
    summary_rows = [
        [Paragraph("<b>Reviewing Physician:</b>", normal), ""],
        [Paragraph("<b>Clinical Findings:</b>",   normal), ""],
        [Paragraph("<b>Interpretation:</b>",      normal), ""],
        [Paragraph("<b>Recommended Action:</b>",  normal), ""],
        [Paragraph("<b>Signature / Date:</b>",    normal), ""],
    ]
    summary_tbl = Table(summary_rows, colWidths=[50*mm, W - 50*mm])
    summary_tbl.setStyle(TableStyle([
        ('GRID',          (0, 0), (-1, -1), 0.5,
         colors.HexColor("#D5D8DC")),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS',(0, 0), (-1, -1), [colors.white, LIGHT_GRAY]),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(summary_tbl)
    story.append(Spacer(1, 5*mm))

    # ── WARNINGS ───────────────────────────────────────────────────────────────
    story.append(section_heading("Important Warnings &amp; Limitations", styles))

    warn_style = ParagraphStyle(
        'warn', parent=styles['Normal'],
        fontSize=8.5, leading=13,
        textColor=colors.HexColor("#7D6608"),
        alignment=TA_JUSTIFY
    )
    warnings = [
        "<b>Clinical Limitation:</b> This ECG was recorded using a single-lead "
        "device. Beat-level classification was generated using a CNN-BiLSTM-based "
        "algorithm and is intended for decision support only. This system does not "
        "replace a standard 12-lead ECG and may not detect ischemia, structural "
        "abnormalities, or all arrhythmias. "
        "<b>Clinical correlation is required.</b>",

        "<b>Regulatory Notice:</b> This device is not approved as a diagnostic "
        "medical device. Results generated by this system must not be used as the "
        "sole basis for any clinical diagnosis or treatment decision. Always consult "
        "a qualified healthcare professional.",
    ]
    for w_text in warnings:
        w_tbl = Table([[Paragraph(w_text, warn_style)]], colWidths=[W])
        w_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), WARNING_BG),
            ('LEFTPADDING',   (0, 0), (-1, -1), 8),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
            ('TOPPADDING',    (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('BOX',           (0, 0), (-1, -1), 1, WARNING_BORDER),
        ]))
        story.append(w_tbl)
        story.append(Spacer(1, 3*mm))

    # ── FOOTER ─────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width=W, thickness=0.5, color=MID_GRAY))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        f"This report was automatically generated by the Heart Attack Prediction "
        f"&amp; Alert System on {now.strftime('%d %B %Y at %H:%M:%S')}. "
        f"For clinical use, physician review is mandatory.",
        ParagraphStyle('footer', parent=styles['Normal'],
                       fontSize=7.5, textColor=MID_GRAY,
                       alignment=TA_CENTER)
    ))

    doc.build(story)

    # Clean up temp ECG plot image after embedding in PDF
    if os.path.exists(plot_path):
        os.remove(plot_path)

    return pdf_path, pdf_filename