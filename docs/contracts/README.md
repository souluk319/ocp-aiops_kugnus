# KOMSCO AIOps Contract Copies

이 폴더는 구현 판단과 검색을 빠르게 하기 위해 공식 PDF 산출물을 Markdown으로 변환해 둔 곳입니다.

- 원본 PDF가 최종 기준입니다.
- Markdown 변환본은 검색용 사본입니다.
- 원본과 변환본이 충돌하면 원본 PDF를 우선합니다.

## 포함 문서

- `Komsco_ai_agent_final.contract.md`: `docs/Komsco_ai_agent_final.pdf` 변환본
- `AIOps-For-OCP.contract.md`: `docs/AIOps-For-OCP.pdf` 변환본

## 재생성

```bash
python3 scripts/convert-contract-pdfs.py
```

## 관련 정리 문서

- `docs/study/aiops-action-plan-e-book.html`: Action Plan 흐름, 검토 기록 저장 위치, 로컬/배포판 확인 방법 정리
