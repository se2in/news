# GitHub Pages 공개 방법

이 프로젝트의 Flask 대시보드는 로컬 PC에서 실행하는 용도입니다. GitHub Pages는 Python/Flask 서버를 실행할 수 없으므로, 공개용 대시보드는 `docs/index.html`과 `docs/earnings.json` 정적 파일로 배포합니다.

## 1. 공개용 대시보드 생성

```powershell
cd "C:\Users\se2in\Desktop\destiny\dify_finance_radar"
python .\export_github_pages.py
```

또는 `publish_github_pages.bat`를 더블클릭합니다.

## 2. GitHub에 올리기

처음 한 번만 실행합니다.

```powershell
git init
git add finance_radar.py earnings_app.py templates requirements.txt config.example.json README.md GITHUB_PAGES_GUIDE.md export_github_pages.py publish_github_pages.bat docs
git commit -m "Add finance radar dashboard"
```

GitHub에서 새 저장소를 만든 뒤, 아래 명령의 주소를 본인 저장소 주소로 바꿔 실행합니다.

```powershell
git remote add origin https://github.com/본인아이디/저장소이름.git
git branch -M main
git push -u origin main
```

## 3. GitHub Pages 켜기

GitHub 저장소에서:

1. Settings
2. Pages
3. Build and deployment
4. Source: Deploy from a branch
5. Branch: `main`
6. Folder: `/docs`
7. Save

잠시 후 `https://본인아이디.github.io/저장소이름/` 주소로 공개됩니다.

## 4. 매번 업데이트할 때

수집 프로그램 실행 후:

```powershell
python .\export_github_pages.py
git add docs\earnings.json
git commit -m "Update earnings dashboard data"
git push
```

주의: `.env`, `finance_radar.sqlite3`, 텔레그램 토큰, Dify 키는 절대 GitHub에 올리지 않습니다. `.gitignore`에 이미 제외되어 있습니다.
