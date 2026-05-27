from __future__ import annotations

from datetime import datetime

from fpdf import FPDF


def _pdf_text(text: str) -> str:
    s = str(text or "")
    # Reemplazar guiones largos y otros caracteres comunes que fallan en latin-1
    s = s.replace("–", "-").replace("—", "-").replace("‘", "'").replace("’", "'").replace("“", "\"").replace("”", "\"")
    try:
        s.encode("latin-1")
        return s
    except Exception:
        return s.encode("latin-1", errors="replace").decode("latin-1")


def _truncate(text: str, max_len: int) -> str:
    s = _pdf_text(text)
    if len(s) <= max_len:
        return s
    if max_len <= 3:
        return s[:max_len]
    return s[: max(0, max_len - 3)] + "..."

def _wrap_lines(pdf: FPDF, text: str, max_width: float) -> list[str]:
    s = _pdf_text(text).replace("\r\n", "\n").replace("\r", "\n")
    if not s:
        return [""]
    lines: list[str] = []
    for part in s.split("\n"):
        words = part.split(" ")
        cur = ""
        for w in words:
            if cur == "":
                cand = w
            else:
                cand = cur + " " + w
            if pdf.get_string_width(cand) <= max_width:
                cur = cand
                continue
            if cur:
                lines.append(cur)
            if pdf.get_string_width(w) <= max_width:
                cur = w
            else:
                chunk = ""
                for ch in w:
                    cand2 = chunk + ch
                    if pdf.get_string_width(cand2) <= max_width:
                        chunk = cand2
                        continue
                    if chunk:
                        lines.append(chunk)
                    chunk = ch
                cur = chunk
        lines.append(cur)
    return [ln if ln is not None else "" for ln in lines] if lines else [""]


def export_findings_pdf(
    output_path: str,
    dataset_name: str,
    run_id: str,
    run_date: str,
    user_email: str,
    total_records: int,
    findings: list[dict],
    total_findings: int | None = None,
    quality_score: int = 0,
    rules_applied: list[str] | None = None,
    rules_passed: list[str] | None = None,
    rules_failed: list[str] | None = None,
    recommendations: list[dict] | None = None,
    ai_insights: list[dict] | None = None,
    ai_recommendations: list[dict] | None = None,
    drift: list[dict] | None = None,
    auto_fix_count: int = 0,
) -> None:
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 8, "Reporte de Inconsistencias Final", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "Sistema: Review Data", ln=True)
    pdf.ln(1)
    pdf.set_draw_color(80, 80, 80)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Resumen ejecutivo", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Dataset: {_truncate(dataset_name, 80)}", ln=True)
    pdf.cell(0, 6, f"Run ID: {run_id}", ln=True)
    pdf.cell(0, 6, f"Fecha: {run_date}", ln=True)
    pdf.cell(0, 6, f"Usuario: {_truncate(user_email, 80)}", ln=True)
    pdf.cell(0, 6, f"Registros analizados: {int(total_records)}", ln=True)
    pdf.cell(0, 6, f"Score de calidad: {int(quality_score)}/100", ln=True)
    total_all = int(total_findings) if total_findings is not None else len(findings)
    if total_all != len(findings):
        pdf.cell(0, 6, f"Inconsistencias: {total_all} · En PDF: {len(findings)}", ln=True)
    else:
        pdf.cell(0, 6, f"Inconsistencias detectadas: {len(findings)}", ln=True)
    ra = rules_applied or []
    rp = rules_passed or []
    rf = rules_failed or []
    if ra:
        pdf.cell(0, 6, f"Reglas aplicadas: {len(ra)}", ln=True)
        pdf.cell(0, 6, f"Reglas cumplidas: {len(rp)}", ln=True)
        pdf.cell(0, 6, f"Reglas fallidas: {len(rf)}", ln=True)
    pdf.ln(3)

    ai_ins = ai_insights or []
    ai_recs = ai_recommendations or []
    ai_drift = drift or []
    if ai_ins or ai_recs or ai_drift or int(auto_fix_count or 0):
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "Resumen ejecutivo IA", ln=True)
        pdf.set_font("Helvetica", "", 10)
        available_w = pdf.w - pdf.l_margin - pdf.r_margin

        if ai_ins:
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(available_w, 5, "Qué pasó (insights):")
            pdf.set_font("Helvetica", "", 10)
            for it in ai_ins[:8]:
                title = _pdf_text(str(it.get("title") or "AI")).strip()
                sev = _pdf_text(str(it.get("severity") or "")).strip()
                desc = _pdf_text(str(it.get("description") or "")).strip()
                if not desc:
                    continue
                prefix = f"- [{sev}] {title}: " if sev else f"- {title}: "
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(available_w, 5, _pdf_text(prefix + desc))
            pdf.ln(1)

        if ai_drift:
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(available_w, 5, "Cambios detectados (drift):")
            pdf.set_font("Helvetica", "", 10)
            for d in ai_drift[:8]:
                dt = _pdf_text(str(d.get("drift_type") or "")).strip()
                field = _pdf_text(str(d.get("field") or "")).strip()
                diff = _pdf_text(str(d.get("difference") or "")).strip()
                sev = _pdf_text(str(d.get("severity") or "")).strip()
                expl = _pdf_text(str(d.get("explanation") or "")).strip()
                line = f"- [{sev}] {dt}"
                if field:
                    line += f" · {field}"
                if diff:
                    line += f" · {diff}"
                if expl:
                    line += f" · {expl}"
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(available_w, 5, _pdf_text(line))
            pdf.ln(1)

        if ai_recs:
            prio_rank = {"Crítica": 0, "Alta": 1, "Media": 2, "Baja": 3}
            sorted_recs = sorted(ai_recs, key=lambda r: prio_rank.get(str(r.get("priority") or "Media"), 2))
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(available_w, 5, "Qué corregir primero (recomendaciones):")
            pdf.set_font("Helvetica", "", 10)
            for r in sorted_recs[:6]:
                pr = _pdf_text(str(r.get("priority") or "")).strip()
                col = _pdf_text(str(r.get("column_name") or "")).strip()
                prob = _pdf_text(str(r.get("problem") or "")).strip()
                rec = _pdf_text(str(r.get("recommendation") or "")).strip()
                impact = _pdf_text(str(r.get("business_impact") or "")).strip()
                head = f"- [{pr}]"
                if col:
                    head += f" {col}"
                if prob:
                    head += f": {prob}"
                if head.strip():
                    pdf.set_x(pdf.l_margin)
                    pdf.multi_cell(available_w, 5, _pdf_text(head))
                if rec:
                    pdf.set_x(pdf.l_margin)
                    pdf.multi_cell(available_w, 5, _pdf_text(f"  Acción: {rec}"))
                if impact:
                    pdf.set_x(pdf.l_margin)
                    pdf.multi_cell(available_w, 5, _pdf_text(f"  Impacto: {impact}"))
            pdf.ln(1)

        if int(auto_fix_count or 0) > 0:
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(available_w, 5, "Siguientes pasos:")
            pdf.set_font("Helvetica", "", 10)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(available_w, 5, f"- Correcciones rápidas detectadas: {int(auto_fix_count)}. Puedes aplicarlas y descargar un CSV corregido desde la app.")
        pdf.ln(2)

    sev_order = ["Cr\u00edtica", "Alta", "Media", "Baja"]
    sev_counts = {s: 0 for s in sev_order}
    for f in findings:
        sev = f.get("severity", "Alta")
        if sev not in sev_counts:
            sev_counts[sev] = 0
        sev_counts[sev] += 1

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Resumen de inconsistencias", ln=True)
    pdf.set_font("Helvetica", "", 10)
    max_count = max([sev_counts.get(s, 0) for s in sev_order] + [1])
    colors = {"Cr\u00edtica": (220, 53, 69), "Alta": (255, 153, 0), "Media": (255, 193, 7), "Baja": (25, 135, 84)}
    chart_x = pdf.l_margin
    chart_w = pdf.w - pdf.l_margin - pdf.r_margin
    bar_h = 6
    gap = 2
    for s in sev_order:
        c = int(sev_counts.get(s, 0) or 0)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(28, bar_h, f"{s}:", border=0)
        fill_w = int((c / max_count) * (chart_w - 28 - 25))
        r, g, b = colors.get(s, (120, 120, 120))
        pdf.set_fill_color(r, g, b)
        pdf.cell(max(1, fill_w), bar_h, "", border=0, fill=True)
        pdf.set_fill_color(230, 230, 230)
        pdf.cell(max(1, (chart_w - 28 - 25) - max(1, fill_w)), bar_h, "", border=0, fill=True)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(25, bar_h, f" {c}", ln=True)
        pdf.ln(gap)
    pdf.ln(1)

    by_field = {}
    for f in findings:
        fld = str(f.get("field", "") or "")
        if not fld:
            continue
        by_field[fld] = int(by_field.get(fld, 0) or 0) + 1
    top_fields = sorted(by_field.items(), key=lambda kv: kv[1], reverse=True)[:10]
    if top_fields:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "Top 10 campos con más inconsistencias", ln=True)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(120, 7, "Campo", border=1)
        pdf.cell(0, 7, "Errores", border=1, ln=True)
        pdf.set_font("Helvetica", "", 9)
        for fld, n in top_fields:
            pdf.cell(120, 6, _truncate(fld, 65), border=1)
            pdf.cell(0, 6, str(int(n)), border=1, ln=True)
        pdf.ln(3)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Detalle de hallazgos", ln=True)

    pdf.set_auto_page_break(auto=False)
    pdf.set_font("Helvetica", "B", 9)
    col_w = [12, 28, 30, 30, 58, 14, 14]
    headers = ["ID", "Campo", "Valor", "Esperado", "Error / Recomendación", "Sev.", "Fila"]
    line_h = 4.5

    def _draw_table_header():
        pdf.set_font("Helvetica", "B", 9)
        for i, h in enumerate(headers):
            pdf.cell(col_w[i], 7, h, border=1)
        pdf.ln()
        pdf.set_font("Helvetica", "", 8)

    def _ensure_space(h: float):
        bottom = pdf.h - pdf.b_margin
        if pdf.get_y() + h <= bottom:
            return
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "Detalle de hallazgos (cont.)", ln=True)
        _draw_table_header()

    _draw_table_header()

    pdf.set_font("Helvetica", "", 8)
    for f in findings:
        fid = str(f.get("id", ""))[:8]
        field = _truncate(str(f.get("field", "")), 60)
        value = _truncate(str(f.get("value", "")), 80)
        expected = _truncate(str(f.get("expected", "")), 80)
        rule = str(f.get("rule_name", "")) or str(f.get("rule_id", ""))
        desc = _truncate(str(f.get("description", "")), 180)
        rec = _truncate(str(f.get("recommendation", "")), 220)
        err = f"{rule}: {desc}"
        if rec:
            err = err + f"\nRecomendación: {rec}"
        sev = str(f.get("severity", "Alta"))
        row_index = "" if f.get("row_index") is None else str(f.get("row_index"))

        row = [fid, field, value, expected, err, sev, row_index]
        lines_by_col: list[list[str]] = []
        for i, txt in enumerate(row):
            max_w = max(1.0, float(col_w[i]) - 2.0)
            lines = _wrap_lines(pdf, str(txt or ""), max_w)
            if len(lines) > 12:
                lines = lines[:11] + ["..."]
            lines_by_col.append(lines)
        row_h = max(len(ls) for ls in lines_by_col) * line_h
        _ensure_space(row_h)

        x0 = pdf.l_margin
        y0 = pdf.get_y()
        for i, lines in enumerate(lines_by_col):
            x = x0 + sum(col_w[:i])
            w = col_w[i]
            pdf.rect(x, y0, w, row_h)
            for j, ln in enumerate(lines):
                pdf.set_xy(x + 1, y0 + j * line_h + 0.6)
                pdf.cell(w - 2, line_h, ln, border=0)
        pdf.set_xy(pdf.l_margin, y0 + row_h)

    pdf.set_auto_page_break(auto=True, margin=12)

    if recommendations:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "Recomendaciones", ln=True)
        pdf.set_font("Helvetica", "", 10)
        available_w = pdf.w - pdf.l_margin - pdf.r_margin
        for rec in recommendations:
            rid = _pdf_text(str(rec.get("rule_id", "") or ""))
            txt = _pdf_text(str(rec.get("recommendation", "") or ""))
            if not txt:
                continue
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(available_w, 5, _pdf_text(f"- {rid}"))
            pdf.set_font("Helvetica", "", 10)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(available_w, 5, _pdf_text(f"  {txt}"))

    pdf.ln(2)
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(0, 5, f"Generado: {datetime.now().strftime('%d-%m-%Y %H:%M')}", ln=True)
    pdf.output(output_path)
