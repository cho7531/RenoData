import json
import os
import re

import pdfplumber
from anthropic import Anthropic

MODEL = "claude-sonnet-5"
MIN_TEXT_LENGTH = 30

COLUMNS = [
    "대지지분",
    "소유자명",
    "생년월일",
    "소유자 신주소",
    "해당필지 지번",
    "호실",
    "대지면적",
    "건축연면적",
    "파일명",
]

SYSTEM_PROMPT = """당신은 한국의 부동산 등기부등본(등기사항전부증명서) 텍스트에서 정비사업 기초 조사에 필요한
정보를 추출하는 전문가입니다. 아래 텍스트는 PDF에서 추출한 등기부등본 원문입니다.

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
      "해당필지_지번": "표제부의 토지 지번(구 지번 표기, 예: OO동 123-4)",
      "호실": "집합건물(아파트/오피스텔/상가 등) 등기부등본인 경우 전유부분의 동/호수 (예: 101동 502호 또는 502호). 토지 등기부등본이거나 호실 정보가 없으면 빈 문자열",
      "대지면적": "표제부에 기재된 대지면적 (단위 포함, 예: 250.5㎡)",
      "건축연면적": "건물 표제부에 기재된 연면적 (단위 포함, 예: 320.4㎡). 건물이 없으면 빈 문자열",
      "owners": [
        {
          "소유자명": "갑구에 기재된 현재 유효한 소유자 성명",
          "생년월일": "소유자의 생년월일 (예: 1970-01-01). 주민등록번호 앞 6자리만 있으면 YYMMDD 형식 그대로 기재",
          "소유자_신주소": "갑구에 기재된 소유자의 주소를 도로명(신주소) 형식으로 기재. 도로명 주소가 없고 지번 주소만 있으면 그 주소를 그대로 기재",
          "대지지분": "해당 소유자의 대지권 비율/지분 (예: 1000분의 123)"
        }
      ]
    }
  ]
}

문서 하나당, 현재 유효한 소유자가 여러 명(공유)인 경우 owners 배열에 각각 별도 항목으로 모두 포함하세요.
소유자 정보를 전혀 찾을 수 없으면 owners를 빈 배열로 두세요. 등기부등본이 한 건뿐이어도 documents 배열에
항목 1개로 넣어서 응답하세요."""


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


def rows_from_structured_info(data, filename):
    documents = data.get("documents") or [data]
    rows = []
    for doc in documents:
        owners = doc.get("owners") or [{}]
        for owner in owners:
            rows.append(
                {
                    "대지지분": owner.get("대지지분", ""),
                    "소유자명": owner.get("소유자명", ""),
                    "생년월일": owner.get("생년월일", ""),
                    "소유자 신주소": owner.get("소유자_신주소", ""),
                    "해당필지 지번": doc.get("해당필지_지번", ""),
                    "호실": doc.get("호실", ""),
                    "대지면적": doc.get("대지면적", ""),
                    "건축연면적": doc.get("건축연면적", ""),
                    "파일명": filename,
                }
            )
    return rows


def process_pdf_file(file_stream, filename):
    """Returns (rows, error). rows is a list of dicts matching COLUMNS, error is None on success."""
    try:
        text = extract_text_from_pdf(file_stream)
    except Exception as exc:
        return [], f"PDF 읽기 실패: {exc}"

    if len(text) < MIN_TEXT_LENGTH:
        return [], "텍스트를 추출할 수 없는 PDF입니다 (스캔본이거나 손상된 파일일 수 있습니다)."

    try:
        data = extract_structured_info(text)
    except json.JSONDecodeError:
        return [], "정보 추출 결과를 해석하지 못했습니다. 다시 시도해주세요."
    except Exception as exc:
        return [], f"정보 추출 실패: {exc}"

    return rows_from_structured_info(data, filename), None
