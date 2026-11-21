import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .constants import MODULE_LABELS, MODULE_FEEDING, MODULE_BIOMETRY, MODULE_HARVEST, MODULE_COLORS

PAGE_MARGIN = 0.6 * inch
AVAILABLE_WIDTH = A4[0] - 2 * PAGE_MARGIN

# Palette
TEAL_DARK = colors.HexColor("#0D4F5C")
TEAL_MID = colors.HexColor("#1A7A8A")
TEAL_LIGHT = colors.HexColor("#2AABB9")
ACCENT = colors.HexColor("#4ECDC4")
GOLD = colors.HexColor("#F4A261")
RED_SOFT = colors.HexColor("#E76F51")
GREEN_SOFT = colors.HexColor("#57CC99")
BG_LIGHT = colors.HexColor("#F0F7F8")
BG_ROW = colors.HexColor("#E8F4F6")
GRAY_TEXT = colors.HexColor("#4A5568")
GRAY_LIGHT = colors.HexColor("#CBD5E0")
WHITE = colors.white

LOGO_PATH = None
logo_candidate = Path(__file__).resolve().parents[4] / "SIG-PISCICOLA-Frontend" / "public" / "images" / "PongaseTrucha.png"
if logo_candidate.exists():
    LOGO_PATH = str(logo_candidate)


# def _lighten_color(color: colors.Color, factor: float = 0.18) -> colors.Color:
#     return colors.Color(
#         min(color.red + (1.0 - color.red) * factor, 1.0),
#         min(color.green + (1.0 - color.green) * factor, 1.0),
#         min(color.blue + (1.0 - color.blue) * factor, 1.0),
#     )


def _get_table_style(header_hex: str | None = None):
    header_color = (
        colors.HexColor(header_hex)
        if isinstance(header_hex, str)
        else header_hex or TEAL_MID
    )
    # table_header_color = _lighten_color(header_color, factor=0.18)
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), TEAL_MID),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.25, GRAY_LIGHT),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, BG_ROW]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("WORDWRAP", (0, 0), (-1, -1), "CJK"),
        ]
    )


def _create_table(data, col_count=None, header_color: str | None = None):
    if not data or len(data) < 1:
        return None
    
    body_style = _styles()["body"]
    header_style = _styles()["table_header"]
    
    formatted_data = []
    for row_index, row in enumerate(data):
        row_style = header_style if row_index == 0 else body_style
        formatted_row = [Paragraph(str(cell), row_style) for cell in row]
        formatted_data.append(formatted_row)
    
    col_count = col_count or len(data[0])
    col_width = AVAILABLE_WIDTH / col_count
    
    table = Table(formatted_data, colWidths=[col_width] * col_count, repeatRows=1)
    table.setStyle(_get_table_style(header_color))
    return table


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Heading1"],
            fontSize=16,
            spaceAfter=12,
            textColor=GRAY_TEXT,
        ),
        "heading": ParagraphStyle(
            "SectionHeading",
            parent=base["Heading2"],
            fontSize=12,
            spaceBefore=14,
            spaceAfter=8,
            textColor=TEAL_DARK,
        ),
        "subheading": ParagraphStyle(
            "SubSectionHeading",
            parent=base["Heading3"],
            fontSize=10,
            spaceBefore=10,
            spaceAfter=6,
            textColor=TEAL_DARK,
        ),
        "body": ParagraphStyle(
            "ReportBody",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            textColor=GRAY_TEXT,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            textColor=WHITE,
            alignment=0,
            spaceAfter=0,
            spaceBefore=0,
        ),
        "meta": ParagraphStyle(
            "ReportMeta",
            parent=base["Normal"],
            fontSize=8.5,
            leading=11,
            textColor=GRAY_TEXT,
        ),
        "note": ParagraphStyle(
            "ReportNote",
            parent=base["Italic"],
            fontSize=9,
            textColor=colors.HexColor("#555555"),
        ),
        "indicator_title": ParagraphStyle(
            "IndicatorTitle",
            parent=base["Heading4"],
            fontSize=9,
            leading=11,
            textColor=TEAL_DARK,
            alignment=1,
        ),
        "indicator_value": ParagraphStyle(
            "IndicatorValue",
            parent=base["Heading2"],
            fontSize=14,
            leading=16,
            textColor=TEAL_DARK,
            alignment=1,
        ),
        "indicator_message": ParagraphStyle(
            "IndicatorMessage",
            parent=base["Normal"],
            fontSize=8.5,
            leading=10,
            textColor=GRAY_TEXT,
            alignment=1,
        ),
    }


def _section_heading_box(text: str, styles: dict, background_color: str | None = None) -> Table:
    label = Paragraph(
        text,
        ParagraphStyle(
            "SectionHeadingBox",
            parent=styles["heading"],
            textColor=WHITE,
            fontSize=12,
            leading=14,
        ),
    )
    table = Table([[label]], colWidths=[AVAILABLE_WIDTH])
    table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    colors.HexColor(background_color)
                    if isinstance(background_color, str)
                    else background_color or TEAL_DARK,
                ),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _build_productivity_indicators(indicators: list[dict], styles: dict) -> list:
    story = []
    if not indicators:
        story.append(Paragraph("No se encontró información para estos indicadores.", styles["note"]))
        return story

    n = max(len(indicators), 1)
    card_width = AVAILABLE_WIDTH / n

    # Alturas fijas → todas las tarjetas tienen exactamente el mismo nivel
    TITLE_ROW_H   = 18
    VALUE_ROW_H   = 28
    MESSAGE_ROW_H = 28

    wrapper_cells = []
    for indicator in indicators:
        title   = Paragraph(indicator.get("name",  "—"), styles["indicator_title"])
        value   = Paragraph(indicator.get("value", "—"), styles["indicator_value"])
        message = Paragraph(indicator.get("notes", ""),  styles["indicator_message"])

        card = Table(
            [[title], [value], [message]],
            colWidths=[card_width - 2],   # -2 para el gap entre tarjetas
            rowHeights=[TITLE_ROW_H, VALUE_ROW_H, MESSAGE_ROW_H],
        )
        card.setStyle(
            TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), WHITE),
                ("BOX",           (0, 0), (-1, -1), 0.5, GRAY_LIGHT),
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING",   (0, 0), (-1, -1), 6),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
                ("TOPPADDING",    (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                # ─── líneas divisoras entre las 3 secciones ───
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, GRAY_LIGHT),   # bajo el título
                ("LINEBELOW", (0, 1), (-1, 1), 0.5, GRAY_LIGHT),   # bajo el valor
            ])
        )
        wrapper_cells.append(card)

    wrapper = Table(
        [wrapper_cells],
        colWidths=[card_width] * n,
        hAlign="CENTER",                 # ← centrado horizontal del bloque completo
    )
    wrapper.setStyle(
        TableStyle([
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),  # ← todas las celdas al mismo nivel
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING",   (0, 0), (-1, -1), 1),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 1),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ])
    )
    story.append(wrapper)
    return story


def _get_logo_path():
    return LOGO_PATH


def _header_footer(canvas, doc):
    canvas.saveState()
    width, height = A4
    header_height = 46 * mm
    canvas.setFillColor(TEAL_DARK)
    canvas.rect(0, height - header_height, width, header_height, fill=1, stroke=0)

    # Decorative circles
    canvas.setFillColor(TEAL_MID)
    canvas.circle(width - 7* mm, height - 15 * mm, 28 * mm, fill=1, stroke=0)
    canvas.setFillColor(TEAL_LIGHT)
    canvas.circle(width - 6 * mm, height - 10 * mm, 16 * mm, fill=1, stroke=0)
    canvas.setFillColor(ACCENT)
    canvas.circle(width - 2 * mm, height - 5 * mm, 8 * mm, fill=1, stroke=0)

    logo_path = _get_logo_path()
    if logo_path:
        try:
            canvas.drawImage(
                logo_path,
                18 * mm,
                height - 38 * mm,
                width=36 * mm,
                height=36 * mm,
                preserveAspectRatio=True,
                mask='auto',
            )
        except Exception:
            pass
    else:
        # simple fish icon fallback
        canvas.setFillColor(ACCENT)
        x = 24 * mm
        y = height - 25 * mm
        canvas.ellipse(x - 8, y - 5, x + 8, y + 5, fill=1, stroke=0)
        p = canvas.beginPath()
        p.moveTo(x - 10, y)
        p.lineTo(x - 18, y + 6)
        p.lineTo(x - 18, y - 6)
        p.close()
        canvas.drawPath(p, fill=1, stroke=0)

    meta = getattr(doc, "report_meta", {})
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 16)
    canvas.drawString(40 * mm, height - 20 * mm, "Reporte histórico del proceso productivo")

    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(WHITE)
    line = (
        f"Lote: {meta.get('batch_code', '—')}  |  Especie: {meta.get('batch_specie', '—')}  |  Estado: {meta.get('batch_status', '—')}"
    )
    if meta.get("farm_name"):
        line += f"  |  Granja: {meta.get('farm_name')} ({meta.get('farm_id', '—')})"
    canvas.drawString(40 * mm, height - 27 * mm, line)

    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GRAY_LIGHT)
    canvas.drawString(
        40 * mm,
        height - 34 * mm,
        f"Generado: {meta.get('generated_at', '—')}  |  Usuario: {meta.get('generated_by', '—')}"
    )

    # Footer
    canvas.setFillColor(TEAL_DARK)
    canvas.rect(0, 0, width, 10 * mm, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(18 * mm, 4 * mm, "Pongase trucha — Gestión Integral de la Producción Piscícola Intensiva (SIG-Piscícola)")
    canvas.drawRightString(width - 18 * mm, 4 * mm, f"Pág. {doc.page}")
    canvas.restoreState()


def _records_to_table(records: list[dict], header_color: str | None = None) -> Table | Paragraph:
    if not records:
        return Paragraph("Sin registros.", _styles()["body"])

    keys = []
    for rec in records:
        for k in rec.keys():
            if k not in keys:
                keys.append(k)

    header = [k.replace("_", " ").title() for k in keys]
    rows = [header]
    for rec in records:
        rows.append([str(rec.get(k, "")) for k in keys])

    return _create_table(rows, col_count=len(keys), header_color=header_color)


def _filter_records_by_type(records: list[dict], type_value: str) -> list[dict]:
    """Filter records by their 'tipo' field."""
    return [r for r in records if r.get("tipo") == type_value]


def _build_feeding_section(records: list[dict], styles: dict, header_color: str | None = None) -> list:
    story = []
    
    if not records:
        story.append(Paragraph("No se encontró información registrada para este módulo.", styles["note"]))
        return story
    
    # Cronogramas (unique programs)
    # Detalles reales de los cronogramas (FeedingSchedule)
    cronograms = _filter_records_by_type(records, "cronograma")
    if cronograms:
        story.append(Paragraph("Detalles de cronogramas", styles["subheading"]))
        cron_rows = [[
            "Nombre",
            "Etapa",
            "Forma alimento",
            "Tamaño pellet (mm)",
            "% Alimentación",
            "Veces/día",
            "Int. raciones (min)",
            "Int. jornadas (días)",
            "FCA esperado",
            "Ganancia diaria (g)",
            "Peso min (g)",
            "Peso max (g)",
            "Comentarios",
        ]]
        for cr in cronograms:
            cron_rows.append([
                cr.get("nombre", "—"),
                cr.get("etapa", "—"),
                cr.get("forma_alimento", "—"),
                cr.get("tamano_pellet_mm", "—"),
                cr.get("porcentaje_alimentacion", "—"),
                str(cr.get("veces_por_dia", "—")),
                str(cr.get("intervalo_entre_raciones_min", "—")),
                str(cr.get("intervalo_entre_jornadas_dias", "—")),
                cr.get("esperado_fca", "—"),
                cr.get("ganancia_diaria_g", "—"),
                cr.get("peso_min_aceptable_g", "—"),
                cr.get("peso_max_aceptable_g", "—"),
                cr.get("comentarios", ""),
            ])
        story.append(_create_table(cron_rows, col_count=len(cron_rows[0]), header_color=header_color))
        story.append(Spacer(1, 0.08 * inch))

    plans = _filter_records_by_type(records, "plan")
    if plans:
        story.append(Paragraph("Cronogramas de alimentación", styles["subheading"]))
        programs = {}
        for plan in plans:
            program_name = plan.get("programa", "—")
            if program_name not in programs:
                programs[program_name] = plan
        
        if programs:
            program_rows = [["Programa", "Ciclo", "Inicio", "Fin"]]
            for prog_name, plan in programs.items():
                program_rows.append([
                    prog_name,
                    plan.get("ciclo", "—"),
                    plan.get("inicio", "—"),
                    plan.get("fin", "—"),
                ])
            story.append(_create_table(program_rows, col_count=4, header_color=header_color))
            story.append(Spacer(1, 0.08 * inch))
    
    # Planes de alimentación
    if plans:
        story.append(Paragraph("Planes de alimentación", styles["subheading"]))
        plan_rows = [["Ciclo", "Programa", "Inicio", "Fin"]]
        for plan in plans:
            plan_rows.append([
                plan.get("ciclo", "—"),
                plan.get("programa", "—"),
                plan.get("inicio", "—"),
                plan.get("fin", "—"),
            ])
        story.append(_create_table(plan_rows, col_count=4, header_color=header_color))
        story.append(Spacer(1, 0.08 * inch))
    
    # Eventos de alimentación
    events = _filter_records_by_type(records, "evento")
    if events:
        story.append(Paragraph("Eventos de alimentación", styles["subheading"]))
        event_rows = [["Ciclo", "Fecha", "Hora", "Ración", "Estado", "Cantidad", "Unidad"]]
        for event in events:
            event_rows.append([
                event.get("ciclo", "—"),
                event.get("fecha", "—"),
                event.get("hora", "—"),
                event.get("racion", "—"),
                event.get("estado", "—"),
                event.get("cantidad", "—"),
                event.get("unidad", "—"),
            ])
        story.append(_create_table(event_rows, col_count=7, header_color=header_color))
        story.append(Spacer(1, 0.08 * inch))
    
    return story


def _build_biometry_section(records: list[dict], styles: dict, header_color: str | None = None) -> list:
    story = []
    
    if not records:
        story.append(Paragraph("No se encontró información registrada para este módulo.", styles["note"]))
        return story
    
    # Controles realizados
    controls = _filter_records_by_type(records, "control")
    if controls:
        story.append(Paragraph("Controles realizados", styles["subheading"]))
        control_rows = [["Ciclo", "Estanque", "Fecha", "Muestra", "Vivos", "Peso Prom (g)", "Mortalidad (%)", "Biomasa (kg)", "FCA"]]
        for control in controls:
            control_rows.append([
                control.get("ciclo", "—"),
                control.get("estanque", "—"),
                control.get("fecha", "—"),
                str(control.get("muestra", "—")),
                str(control.get("vivos", "—")),
                str(control.get("peso_prom_g", "—")),
                str(control.get("mortalidad_%", "—")),
                str(control.get("biomasa_kg", "—")),
                str(control.get("fca", "—")),
            ])
        story.append(_create_table(control_rows, col_count=9, header_color=header_color))
        story.append(Spacer(1, 0.08 * inch))
    
    # Evaluaciones realizadas
    evaluations = _filter_records_by_type(records, "evaluacion")
    if evaluations:
        story.append(Paragraph("Evaluaciones realizadas", styles["subheading"]))
        eval_rows = [["Ciclo", "Estanque", "Fecha", "Muestra", "Peso Prom (g)", "Mortalidad"]]
        for eval in evaluations:
            eval_rows.append([
                eval.get("ciclo", "—"),
                eval.get("estanque", "—"),
                eval.get("fecha", "—"),
                str(eval.get("muestra", "—")),
                str(eval.get("peso_prom_g", "—")),
                str(eval.get("mortalidad", "—")),
            ])
        story.append(_create_table(eval_rows, col_count=6, header_color=header_color))
        story.append(Spacer(1, 0.08 * inch))
    
    return story


def _build_harvest_section(records: list[dict], styles: dict, header_color: str | None = None) -> list:
    story = []
    if not records:
        story.append(Paragraph("No se encontró información registrada para este módulo.", styles["note"]))
        return story

    # Cosechas
    harvests = _filter_records_by_type(records, "cosecha")
    if harvests:
        story.append(Paragraph("Cosechas", styles["subheading"]))
        harvest_rows = [["Ciclo", "Fecha", "Tipo Cosecha", "Peces", "Peso Total G"]]
        for h in harvests:
            harvest_rows.append([
                h.get("ciclo", "—"),
                h.get("fecha", "—"),
                h.get("tipo_cosecha", "—"),
                str(h.get("peces", "—")),
                str(h.get("peso_total_g", "—")),
            ])
        story.append(_create_table(harvest_rows, col_count=len(harvest_rows[0]), header_color=header_color))
        story.append(Spacer(1, 0.08 * inch))

    # Fuentes de cosecha
    sources = _filter_records_by_type(records, "fuente_cosecha")
    if sources:
        story.append(Paragraph("Fuentes de cosecha", styles["subheading"]))
        src_rows = [["Cosecha Id", "Peces", "Peso G", "Trazabilidad"]]
        for s in sources:
            src_rows.append([
                str(s.get("cosecha_id", "—")),
                str(s.get("peces", "—")),
                str(s.get("peso_g", "—")),
                s.get("trazabilidad", "—"),
            ])
        story.append(_create_table(src_rows, col_count=len(src_rows[0]), header_color=header_color))
        story.append(Spacer(1, 0.08 * inch))

    # Clasificaciones
    clas = _filter_records_by_type(records, "clasificacion")
    if clas:
        story.append(Paragraph("Clasificaciones", styles["subheading"]))
        cls_rows = [["Cosecha Id", "Categoría", "Peces", "Peso G"]]
        for c in clas:
            cls_rows.append([
                str(c.get("cosecha_id", "—")),
                c.get("categoria", "—"),
                str(c.get("peces", "—")),
                str(c.get("peso_g", "—")),
            ])
        story.append(_create_table(cls_rows, col_count=len(cls_rows[0]), header_color=header_color))
        story.append(Spacer(1, 0.08 * inch))

    # Derivaciones de lote
    deriv = _filter_records_by_type(records, "derivacion_lote")
    if deriv:
        story.append(Paragraph("Derivaciones de lote", styles["subheading"]))
        drv_rows = [["Clasificacion Id", "Peces", "Peso G"]]
        for d in deriv:
            drv_rows.append([
                str(d.get("clasificacion_id", "—")),
                str(d.get("peces", "—")),
                str(d.get("peso_g", "—")),
            ])
        story.append(_create_table(drv_rows, col_count=len(drv_rows[0]), header_color=header_color))
        story.append(Spacer(1, 0.08 * inch))

    return story


def export_production_report_pdf(report_data: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=52 * mm,
        bottomMargin=20 * mm,
    )
    styles = _styles()
    story = []

    batch = report_data["batch"]
    doc.report_meta = {
        "batch_code": batch.get("code", "—"),
        "batch_specie": batch.get("specie", "—"),
        "batch_status": batch.get("status", "—"),
        "farm_id": batch.get("farm_id", "—"),
        "farm_name": batch.get("farm_name", "—"),
        "generated_at": report_data.get("generated_at", "—"),
        "generated_by": report_data.get("generated_by", "—"),
    }
    story.append(Spacer(1, 0.1 * inch))

    traceability = report_data.get("traceability", {})
    story.append(
        _section_heading_box(
            "Origen y trazabilidad del lote", styles, background_color=TEAL_DARK
        )
    )
    story.append(Spacer(1, 4 * mm))

    origin_rows = [["Lote", "Origen", "Fecha", "Proveedor", "Documento", "Compra/Factura"]]
    for origin in traceability.get("origins", []):
        origin_rows.append(
            [
                origin.get("batch_code", "—"),
                "Compra" if origin.get("type") == "purchase" else "Registro inicial",
                origin.get("date", "—"),
                origin.get("supplier") or "—",
                origin.get("supplier_document") or "—",
                origin.get("invoice_number") or origin.get("purchase_id") or "—",
            ]
        )
    if len(origin_rows) > 1:
        story.append(_create_table(origin_rows, col_count=6))
        story.append(Spacer(1, 0.08 * inch))

    genealogy_rows = [["Lote padre", "Lote derivado", "Cantidad"]]
    for link in traceability.get("genealogy", []):
        genealogy_rows.append(
            [link["parent_code"], link["child_code"], link["quantity"]]
        )
    if len(genealogy_rows) > 1:
        story.append(Paragraph("Genealogía", styles["subheading"]))
        story.append(_create_table(genealogy_rows, col_count=3))
        story.append(Spacer(1, 0.08 * inch))

    movement_rows = [["Fecha", "Origen", "Destino", "Cantidad", "Motivo"]]
    for transfer in traceability.get("transfers", []):
        movement_rows.append(
            [
                transfer["date"],
                transfer["from_pond"],
                transfer["to_pond"],
                transfer["quantity"],
                transfer["reason"],
            ]
        )
    if len(movement_rows) > 1:
        story.append(Paragraph("Movimientos entre estanques", styles["subheading"]))
        story.append(_create_table(movement_rows, col_count=5))
        story.append(Spacer(1, 0.08 * inch))

    growth_rows = [["Fecha", "Ciclo", "Peso mín. (g)", "Peso prom. (g)", "Peso máx. (g)", "Mortalidad"]]
    for point in traceability.get("growth", []):
        growth_rows.append(
            [
                point["date"],
                point["cycle"],
                point["min_weight_g"],
                point["avg_weight_g"],
                point["max_weight_g"],
                point["mortality_quantity"],
            ]
        )
    if len(growth_rows) > 1:
        story.append(Paragraph("Crecimiento registrado", styles["subheading"]))
        story.append(_create_table(growth_rows, col_count=6))
        story.append(Spacer(1, 0.12 * inch))

    story.append(_section_heading_box("Indicadores de productividad", styles, background_color=TEAL_DARK))
    story.append(Spacer(1, 4 * mm))
    story.extend(_build_productivity_indicators(report_data.get("productivity_indicators", []), styles))
    story.append(Spacer(1, 0.15 * inch))

    ctx = report_data["context"]
    if ctx.get("cycles"):
        story.append(_section_heading_box("Ciclos asociados", styles, background_color=TEAL_DARK))
        story.append(Spacer(1, 4 * mm))
        cycle_rows = [["Ciclo", "Estanque", "Estado", "Inicio", "Fin"]]
        for c in ctx["cycles"]:
            cycle_rows.append(
                [c["name"], c["pond"], c["state"], c["start_date"], c["finish_date"] or "—"]
            )
        cycle_table = _create_table(cycle_rows, col_count=5)
        if cycle_table:
            story.append(cycle_table)
        story.append(Spacer(1, 0.1 * inch))

    for module_key in report_data["selected_modules"]:
        mod = report_data["modules"][module_key]
        module_color = MODULE_COLORS.get(module_key) or TEAL_DARK
        story.append(_section_heading_box(mod["label"], styles, background_color=module_color))
        story.append(Spacer(1, 4 * mm))

        if module_key == MODULE_FEEDING:
            story.extend(_build_feeding_section(mod["records"], styles, header_color=module_color))
        elif module_key == MODULE_BIOMETRY:
            story.extend(_build_biometry_section(mod["records"], styles, header_color=module_color))
        elif module_key == MODULE_HARVEST:
            story.extend(_build_harvest_section(mod["records"], styles, header_color=module_color))
        else:
            if mod["has_data"]:
                table = _records_to_table(mod["records"], header_color=module_color)
                if table:
                    story.append(table)
            else:
                story.append(
                    Paragraph(
                        "No se encontró información registrada para este módulo "
                        "en el alcance consultado.",
                        styles["note"],
                    )
                )
        story.append(Spacer(1, 0.12 * inch))

    if report_data["empty_module_labels"]:
        story.append(Paragraph("Módulos sin información registrada", styles["heading"]))
        labels = ", ".join(report_data["empty_module_labels"])
        story.append(
            Paragraph(
                f"Los siguientes módulos fueron seleccionados pero no contaron "
                f"con registros: <b>{labels}</b>.",
                styles["note"],
            )
        )

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    buffer.seek(0)
    return buffer.getvalue()
