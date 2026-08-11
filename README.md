# 등기부등본 자동 추출

등기부등본 PDF를 업로드하면 지번, 면적, 소유자명, 생년월일, 주소, 대지지분, 소유건축연면적을 자동 추출하여 엑셀(.xlsx)로 다운로드하는 웹 앱입니다.

## 설치

```
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

## API 키 설정

`.env.example`을 복사해 `.env` 파일을 만들고 Anthropic API 키를 입력하세요.

```
copy .env.example .env
```

`.env` 파일 내용:
```
ANTHROPIC_API_KEY=발급받은_키
```

## 실행

```
venv\Scripts\python app.py
```

브라우저에서 http://127.0.0.1:5000 접속 후 PDF 파일을 업로드하면 됩니다.

## 동작 방식

1. `pdfplumber`로 PDF에서 텍스트를 추출합니다 (정부24/인터넷등기소에서 발급한 텍스트 기반 PDF 지원).
2. 추출한 텍스트를 Claude API에 전달해 지번/면적/소유자 정보를 구조화된 JSON으로 받습니다.
3. 소유자가 여러 명(공유)인 경우 각 소유자마다 한 행씩 생성됩니다.
4. `openpyxl`로 엑셀 파일을 생성해 다운로드합니다.

스캔본처럼 텍스트가 없는 PDF는 추출이 되지 않으며, 해당 파일은 오류 목록에 표시됩니다.
