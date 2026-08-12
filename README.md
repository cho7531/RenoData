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

## GitHub / Vercel 배포

### 1. 파일 구성
- `app.py`: Flask 웹 앱 진입점
- `templates/index.html`: 웹 UI 템플릿
- `static/`: CSS, JavaScript 정적 자원
- `requirements.txt`: 배포용 Python 패키지 목록
- `vercel.json`: Vercel 서버리스 빌드/라우팅 설정
- `.env.example`: 배포 전 복사하여 `ANTHROPIC_API_KEY`를 설정할 파일

### 2. Vercel에 배포하기
1. GitHub 저장소를 Vercel에 연결합니다.
2. Vercel 프로젝트 설정에서 `Root Directory`를 이 저장소 루트로 지정합니다.
3. 환경 변수에 다음 값을 추가합니다:
   - `ANTHROPIC_API_KEY` = 발급받은 Anthropic API 키
4. 배포를 시작하면 Vercel이 `vercel.json`을 참조하여 `app.py`를 Python 서버리스 함수로 빌드합니다.
5. 배포가 완료되면 Vercel에서 제공하는 URL로 웹 앱에 접근할 수 있습니다.

### 3. 필수 설정
- `requirements.txt`에 필요한 패키지가 명시되어 있어야 합니다.
- `.env` 파일은 GitHub에 커밋하지 말고 로컬 개발에서만 사용합니다.
- Vercel에서는 `.env` 대신 프로젝트 환경 변수 설정을 사용해야 합니다.

### 4. vercel.json 구성
```json
{
  "builds": [
    { "src": "app.py", "use": "@vercel/python" }
  ],
  "routes": [
    { "src": "(.*)", "dest": "app.py" }
  ]
}
```

### 5. 배포 후 확인
- Vercel에서 배포 로그에 빌드 성공 메시지가 있는지 확인합니다.
- 웹 앱이 정상적으로 열리고 PDF 업로드/추출/다운로드 기능이 동작하는지 확인합니다.
- `ANTHROPIC_API_KEY`가 누락되면 추출 API 호출 시 오류가 발생합니다.

## 동작 방식

1. `pdfplumber`로 PDF에서 텍스트를 추출합니다 (정부24/인터넷등기소에서 발급한 텍스트 기반 PDF 지원).
2. 추출한 텍스트를 Claude API에 전달해 지번/면적/소유자 정보를 구조화된 JSON으로 받습니다.
3. 소유자가 여러 명(공유)인 경우 각 소유자마다 한 행씩 생성됩니다.
4. `openpyxl`로 엑셀 파일을 생성해 다운로드합니다.

스캔본처럼 텍스트가 없는 PDF는 추출이 되지 않으며, 해당 파일은 오류 목록에 표시됩니다.

<!-- git-connect test 1786537346 -->
