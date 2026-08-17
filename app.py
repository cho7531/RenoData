import io
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_file

load_dotenv()

from excel_generator import build_excel
from extractor import COLUMNS, lookup_postal_codes, process_pdf_file

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024 * 1024  # 10GB total request cap

MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB per file
MAX_FILES = 50


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/extract", methods=["POST"])
def api_extract():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "업로드된 파일이 없습니다."}), 400

    if len(files) > MAX_FILES:
        return jsonify({"error": f"한 번에 최대 {MAX_FILES}개 파일까지 처리할 수 있습니다."}), 400

    all_rows = []
    errors = []

    for f in files:
        filename = f.filename or "unknown.pdf"

        if not filename.lower().endswith(".pdf"):
            errors.append({"filename": filename, "message": "PDF 파일만 지원합니다."})
            continue

        f.stream.seek(0, os.SEEK_END)
        size = f.stream.tell()
        f.stream.seek(0)
        if size > MAX_FILE_SIZE:
            errors.append({"filename": filename, "message": "파일 크기가 500MB를 초과합니다."})
            continue

        rows, error = process_pdf_file(f.stream, filename)
        if error:
            errors.append({"filename": filename, "message": error})
        else:
            all_rows.extend(rows)

    return jsonify({"columns": COLUMNS, "rows": all_rows, "errors": errors})


@app.route("/api/download", methods=["POST"])
def api_download():
    payload = request.get_json(silent=True) or {}
    rows = payload.get("rows")
    if not rows:
        return jsonify({"error": "다운로드할 데이터가 없습니다."}), 400

    buffer = build_excel(rows)
    return send_file(
        buffer,
        as_attachment=True,
        download_name="등기부등본_추출결과.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/api/postal-codes", methods=["POST"])
def api_postal_codes():
    payload = request.get_json(silent=True) or {}
    rows = payload.get("rows")
    if not rows:
        return jsonify({"error": "업데이트할 데이터가 없습니다."}), 400

    addresses = [
        row.get("소유자 주소", "")
        for row in rows
        if row.get("소유자 주소") and not row.get("우편번호")
    ]
    postal_codes = lookup_postal_codes(addresses)
    for row in rows:
        addr = row.get("소유자 주소", "")
        if addr and not row.get("우편번호"):
            row["우편번호"] = postal_codes.get(addr.strip(), "")

    return jsonify({"rows": rows})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
