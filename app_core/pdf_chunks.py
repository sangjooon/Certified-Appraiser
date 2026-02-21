import io
from typing import List, Tuple

import pandas as pd

def split_pdf_into_chunks(
    pdf_bytes: bytes, chunk_size: int = 10
    ) -> List[Tuple[bytes, int, int]]:
    """
    PDF bytes를 chunk_size 페이지 단위로 쪼개서
    [(chunk_pdf_bytes, start_page(1-indexed), end_page(1-indexed)), ...] 형태로 반환
    """
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        # 예전 환경 호환용
        from PyPDF2 import PdfReader, PdfWriter  # type: ignore

    reader = PdfReader(io.BytesIO(pdf_bytes))
    total_pages = len(reader.pages)
    chunks: List[Tuple[bytes, int, int]] = []

    for start in range(0, total_pages, chunk_size):
        end = min(start + chunk_size, total_pages)

        writer = PdfWriter()
        for i in range(start, end):
            writer.add_page(reader.pages[i])

        buf = io.BytesIO()
        writer.write(buf)
        chunks.append((buf.getvalue(), start + 1, end))

    return chunks


# ==========================================
# 0 - 2. 엑셀 bytes 만드는 함수 (유틸)
# ==========================================
def make_excel_bytes(extracted_data: dict) -> bytes:
    df = pd.DataFrame([extracted_data])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()


# ==========================================
# 0 - 3. "전체 처리"를 함수로 묶기 (유틸)
# ==========================================
