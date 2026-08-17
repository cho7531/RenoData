import base64
import json
import os
import re

import pymupdf as fitz
import pdfplumber
from anthropic import Anthropic

MODEL = "claude-sonnet-5"
MIN_TEXT_LENGTH = 30
RENDER_MAX_EDGE = 1568  # Anthropic's recommended max long-edge for vision input
RENDER_JPEG_QUALITY = 85
MAX_SCANNED_PAGES = 400  # sanity cap against pathological files, not a real-world limit
SCAN_BATCH_PAGES = 20  # pages per vision call, to stay well under the request size limit

COLUMNS = [
    "호수연번",
    "토지등소유자번호",
    "공동지분",
    "이름",
    "생년월일",
    "소유자 주소",
    "우편번호",
    "연락처",
    "해당번지",
    "주택명",
    "동명",
    "호수",
    "지번면적",
    "소유 토지면적",
    "건축물용도",
    "건축물소유연면적",
]

# Fields that live on the property/unit itself rather than on an individual
# owner. Shown once per unit (on the first owner's row) in the final output.
UNIT_FIELDS = [
    "해당번지",
    "주택명",
    "동명",
    "호수",
    "지번면적",
    "소유 토지면적",
    "건축물용도",
    "건축물소유연면적",
]

SYSTEM_PROMPT = """당신은 한국의 부동산 등기부등본(등기사항전부증명서) 텍스트에서 정비사업 조합원 명부 작성에
필요한 정보를 추출하는 전문가입니다. 아래 텍스트는 PDF에서 추출한 등기부등본 원문입니다.

중요: 하나의 PDF 파일 안에 서로 다른 부동산에 대한 등기부등본이 여러 건 이어 붙어 있을 수 있습니다
(예: 여러 필지/호실을 한 번에 발급받아 하나의 파일로 합친 경우). 각 등기부등본은 보통 "등기사항전부증명서"
제목과 함께 별도의 [표제부]로 시작합니다. 텍스트 전체를 훑어 등기부등본이 몇 건 있는지 먼저 판단하고,
각 건을 documents 배열의 별도 항목으로 빠짐없이 분리해서 추출하세요. 절대 첫 번째 건만 추출하고 나머지를
누락하지 마세요.

각 등기부등본은 특정 시점에 발급된 문서입니다. 반드시 "발급 시점 기준으로 유효한 현재 상태"만 추출하세요.
갑구(소유권에 관한 사항)에는 시간순으로 여러 건의 소유권보존/이전 이력이 기재되어 있을 수 있습니다.
그 중 이후 순위번호에 의해 말소(취소)되지 않고 최종적으로 유효한, 가장 마지막 소유권 항목의 소유자만 추출하세요.
매도/이전되어 더 이상 소유자가 아닌 과거(이전) 소유자는 절대 포함하지 마세요. 다만 같은 시점에 지분을 나누어
함께 소유하는 공유자(예: 부부 공동명의)는 모두 현재 소유자이므로 전부 포함하세요.

다음 JSON 스키마에 맞춰 정확한 값만 추출하세요. 값을 찾을 수 없으면 빈 문자열("")로 두세요.
추측하거나 값을 지어내지 마세요. 반드시 JSON만 출력하고 다른 설명은 절대 추가하지 마세요.

{
  "documents": [
    {
      "해당번지": "대지권의 목적인 토지의 지번. 여러 필지면 쉼표로 나열 (예: 2524-2, 2523-10)",
      "주택명": "공동주택/연립주택 등의 건물(단지) 이름 (예: 세방)",
      "동명": "동 표시. 숫자형(예: 101동)이든 문자형(예: 가동)이든 표시된 그대로",
      "호수": "전유부분의 호수만 (예: 101, 502). 동 표시는 제외하고 숫자만",
      "지번면적": "표제부에 기재된 해당 토지(지번)의 전체 면적 (단위 포함, 예: 250.5㎡)",
      "건축물용도": "건물 표제부에 기재된 건축물의 용도 (예: 공동주택, 근린생활시설)",
      "건축물소유연면적": "전유부분 건물의 표시에 기재된 이 호실 전용 면적 (단위 포함, 예: 84.98㎡). 건물이 없으면 빈 문자열",
      "대지권비율": "이 호실의 대지권 비율. 등기부에 기재된 형식 그대로 (예: 10000분의 55)",
      "owners": [
        {
          "이름": "갑구에 기재된 현재 유효한 소유자 성명",
          "생년월일": "소유자의 생년월일 (예: 1970-01-01). 주민등록번호 앞 6자리만 있으면 YYMMDD 형식 그대로 기재",
          "주소": "갑구에 기재된 소유자의 주소를 등기부에 표시된 형식 그대로 기재 (도로명, 괄호 안 종전주소 등 원문 그대로)",
          "공동지분": "이 호실을 여러 명이 공유하는 경우, 공유자들 사이의 지분 비율 (등기부의 '공유자 지분 O분의 O' 표기를 O/O 형식으로, 예: 1/2). 소유자가 1명뿐이면 빈 문자열"
        }
      ]
    }
  ]
}

문서 하나당, 현재 유효한 소유자가 여러 명(공유)인 경우 owners 배열에 각각 별도 항목으로 모두 포함하세요.
소유자 정보를 전혀 찾을 수 없으면 owners를 빈 배열로 두세요. 등기부등본이 한 건뿐이어도 documents 배열에
항목 1개로 넣어서 응답하세요.

주의: "대지권비율"(예: 10000분의 55, 건물 전체 대지 중 이 호실의 몫)과 "공동지분"(예: 1/2, 이 호실을
공유하는 소유자들 사이의 지분)은 서로 다른 개념입니다. 혼동하지 마세요."""

POSTAL_SYSTEM_PROMPT = """당신은 대한민국 도로명주소 우편번호(5자리 새 우편번호)를 추정하는 전문가입니다.
아래 목록에 주어진 각 주소에 대해 우편번호를 반환하세요. 확실히 알지 못하는 주소는 절대 추측해서 지어내지 말고
빈 문자열("")로 두세요. 반드시 아래 형식의 JSON 객체만 출력하고 다른 설명은 추가하지 마세요.

{"주소1": "12345", "주소2": ""}"""


def _get_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다. .env 파일을 확인해주세요."
        )
    return Anthropic(api_key=api_key)


def extract_text_from_pdf(file_stream):
    text_parts = []
    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
    return "\n".join(text_parts).strip()


def render_pdf_pages_to_images(file_stream):
    """Rasterizes each page of a (possibly scanned/text-less) PDF into a
    base64-encoded JPEG, for feeding to Claude's vision input instead of text.
    Pages are scaled so their long edge matches Anthropic's recommended max
    (larger images are auto-downscaled server-side anyway, but sending them
    already-sized keeps the request well under the API's size limit)."""
    file_stream.seek(0)
    pdf_bytes = file_stream.read()
    images = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc[:MAX_SCANNED_PAGES]:
            long_edge = max(page.rect.width, page.rect.height)
            zoom = RENDER_MAX_EDGE / long_edge if long_edge > 0 else 1
            matrix = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix)
            jpeg_bytes = pix.tobytes("jpg", jpg_quality=RENDER_JPEG_QUALITY)
            images.append(base64.b64encode(jpeg_bytes).decode("ascii"))
    return images


def _parse_json_response(raw_text):
    cleaned = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    return json.loads(cleaned)


def extract_structured_info(pdf_text):
    client = _get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": pdf_text[:60000]}],
    )
    raw_text = "".join(
        block.text for block in response.content if block.type == "text"
    )
    return _parse_json_response(raw_text)


def extract_structured_info_from_images(images):
    client = _get_client()
    content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": img,
            },
        }
        for img in images
    ]
    content.append(
        {
            "type": "text",
            "text": "위 이미지는 등기부등본 스캔본 페이지들입니다. 이미지 속 텍스트를 읽어 시스템 프롬프트의 JSON 스키마에 맞춰 추출하세요.",
        }
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    raw_text = "".join(
        block.text for block in response.content if block.type == "text"
    )
    return _parse_json_response(raw_text)


def extract_structured_info_from_scanned_pdf(images):
    """Runs vision extraction in batches so PDFs with many merged 등기부등본
    documents (and therefore many pages) stay under the API's per-request
    size/token limits, then merges each batch's documents into one list."""
    all_documents = []
    for start in range(0, len(images), SCAN_BATCH_PAGES):
        batch = images[start : start + SCAN_BATCH_PAGES]
        data = extract_structured_info_from_images(batch)
        all_documents.extend(data.get("documents") or [data])
    return {"documents": all_documents}


def lookup_postal_codes(addresses):
    """Given a list of Korean addresses, returns a dict mapping each unique,
    non-empty address to a best-effort 5-digit postal code (or "" if unknown)."""
    unique_addresses = sorted({a.strip() for a in addresses if a and a.strip()})
    if not unique_addresses:
        return {}

    client = _get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=POSTAL_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": "\n".join(unique_addresses)}],
    )
    raw_text = "".join(
        block.text for block in response.content if block.type == "text"
    )
    try:
        result = _parse_json_response(raw_text)
    except json.JSONDecodeError:
        return {}
    return result if isinstance(result, dict) else {}


def _parse_area(text):
    if not text:
        return None
    match = re.search(r"[\d,]+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _parse_ratio(text):
    """Parses Korean '분모분의분자' notation (e.g. '10000분의 55') or 'a/b'."""
    if not text:
        return None
    match = re.search(r"([\d,]+(?:\.\d+)?)\s*분의\s*([\d,]+(?:\.\d+)?)", text)
    if match:
        denominator, numerator = match.groups()
    else:
        match = re.search(r"([\d,]+(?:\.\d+)?)\s*/\s*([\d,]+(?:\.\d+)?)", text)
        if not match:
            return None
        numerator, denominator = match.groups()
    try:
        denominator = float(denominator.replace(",", ""))
        numerator = float(numerator.replace(",", ""))
        if denominator == 0:
            return None
        return numerator / denominator
    except ValueError:
        return None


def _compute_owned_land_area(site_area_text, ratio_text):
    area = _parse_area(site_area_text)
    ratio = _parse_ratio(ratio_text)
    if area is None or ratio is None:
        return ""
    return f"{area * ratio:.4f}"


def rows_from_structured_info(data, filename):
    documents = data.get("documents") or [data]
    rows = []
    for doc_idx, doc in enumerate(documents):
        owned_land_area = _compute_owned_land_area(
            doc.get("지번면적", ""), doc.get("대지권비율", "")
        )
        owners = doc.get("owners") or [{}]
        multi_owner = len(owners) > 1
        group_key = f"{filename}#{doc_idx}"
        for owner in owners:
            rows.append(
                {
                    "_group": group_key,
                    "호수연번": "",
                    "토지등소유자번호": "",
                    "공동지분": owner.get("공동지분", "") if multi_owner else "",
                    "이름": owner.get("이름", ""),
                    "생년월일": owner.get("생년월일", ""),
                    "소유자 주소": owner.get("주소", ""),
                    "우편번호": "",
                    "연락처": "",
                    "해당번지": doc.get("해당번지", ""),
                    "주택명": doc.get("주택명", ""),
                    "동명": doc.get("동명", ""),
                    "호수": doc.get("호수", ""),
                    "지번면적": doc.get("지번면적", ""),
                    "소유 토지면적": owned_land_area,
                    "건축물용도": doc.get("건축물용도", ""),
                    "건축물소유연면적": doc.get("건축물소유연면적", ""),
                }
            )
    return rows


def process_pdf_file(file_stream, filename):
    """Returns (rows, error). rows is a list of dicts matching COLUMNS (plus an
    internal "_group" key), error is None on success."""
    try:
        text = extract_text_from_pdf(file_stream)
    except Exception as exc:
        return [], f"PDF 읽기 실패: {exc}"

    if len(text) < MIN_TEXT_LENGTH:
        try:
            images = render_pdf_pages_to_images(file_stream)
        except Exception as exc:
            return [], f"스캔본 이미지 변환 실패: {exc}"

        if not images:
            return [], "텍스트를 추출할 수 없는 PDF입니다 (손상된 파일일 수 있습니다)."

        try:
            data = extract_structured_info_from_scanned_pdf(images)
        except json.JSONDecodeError:
            return [], "정보 추출 결과를 해석하지 못했습니다. 다시 시도해주세요."
        except Exception as exc:
            return [], f"스캔본 정보 추출 실패: {exc}"

        return rows_from_structured_info(data, filename), None

    try:
        data = extract_structured_info(text)
    except json.JSONDecodeError:
        return [], "정보 추출 결과를 해석하지 못했습니다. 다시 시도해주세요."
    except Exception as exc:
        return [], f"정보 추출 실패: {exc}"

    return rows_from_structured_info(data, filename), None
