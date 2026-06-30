# Mock Customer Ops Pack

가상 고객사 `MockPay 운영센터`의 운영 문서 세트다.

목적은 실제 고객 문서를 받기 전에도 PDF parsing, 전처리, RAG 적재, 검색, citation 시나리오를 운영 관점으로 연습하는 것이다.

## 문서

| 원본 | 용도 |
| --- | --- |
| `src/00-service-map.md` | 서비스/namespace/운영 경계 |
| `src/01-incident-runbook.md` | CrashLoopBackOff, ImagePullBackOff, 지연 알림 runbook |
| `src/02-change-approval-policy.md` | 변경창, 승인, read-only 경계 |
| `src/03-incident-retrospective-2025.md` | 일부러 stale 처리한 과거 장애 리포트 |

PDF는 생성물이다.

```bash
python3 scripts/build-mock-customer-pdfs.py
task kugnus:rag:mock-customer:smoke
```

PDF 생성은 repo 밖 venv `/home/kugnus/.local/share/kugnus-pdf-tools/.venv`의 open source `reportlab`을 사용한다. 한글 폰트는 기본적으로 `/mnt/c/Windows/Fonts/malgun.ttf`를 embed한다.

skipped: OCR/scanned PDF. add when real customer image PDFs arrive.
