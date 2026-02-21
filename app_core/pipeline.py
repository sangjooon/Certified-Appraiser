import json
from typing import Callable, Optional

from .extraction import extract_data_by_rules, extract_pdf_category
from .ocr_client import call_naver_ocr, json_to_text_lines
from .pdf_chunks import make_excel_bytes, split_pdf_into_chunks

def process_pdf(
    file_bytes, api_url, secret_key, progress_cb: Optional[Callable] = None
    ):
    # 1) PDF를 10페이지씩 분할
    chunks = split_pdf_into_chunks(file_bytes, chunk_size=10)

    all_raw_text_parts = []
    for idx, (chunk_bytes, start_p, end_p) in enumerate(chunks, start=1):
        if progress_cb:
            progress_cb(idx, len(chunks), start_p, end_p)

        result = call_naver_ocr(chunk_bytes, "pdf", api_url, secret_key)
        if not result["ok"]:
            raise RuntimeError(
                f"OCR 실패 (페이지 {start_p}~{end_p}): {result.get('status_code')}\n{result.get('text') or result.get('error')}"
            )

        ocr_json = result["json"]
        if not ocr_json:
            raise RuntimeError(
                f"OCR JSON 파싱 실패 (페이지 {start_p}~{end_p})\n{result.get('text')}"
            )

        chunk_text = json_to_text_lines(ocr_json)
        all_raw_text_parts.append(
            f"\n######## PDF PAGES {start_p}-{end_p} ########\n{chunk_text}".strip()
        )
    # 루프 끝난 뒤
    if progress_cb:
        progress_cb(len(chunks), len(chunks), 0, 0)

    raw_text = "\n\n".join(all_raw_text_parts)
    # 2) 규칙 기반 데이터 추출
    extracted_data = extract_data_by_rules(raw_text, extract_pdf_category(raw_text))
    excel_bytes = make_excel_bytes(extracted_data)

    return raw_text, extracted_data, excel_bytes


# ==========================================
# 1. [설정] 네이버 API 연결
# ==========================================
