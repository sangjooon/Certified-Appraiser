# 이 코드는 개발용 코드임
# 0.0.4version
# 토지


import streamlit as st
import requests
import pandas as pd
import uuid
import time
import json
import re
import io
import hashlib

from typing import Callable, Optional, List, Tuple, Sequence


# ==========================================
# 0 - 0. 글자 자르기 함수
# ==========================================
# 첫 문자열 포함 마지막 문자열 미포함
def slice_between(
    text: str,
    start: str,
    end: Optional[str] = None,
    *,
    include_start: bool = True,
    include_end: bool = False,
    flags: int = 0,
    ) -> str:
    """
    text에서 start ~ end 구간을 잘라 반환.
    - end가 None이면 start부터 끝까지
    - include_start/include_end로 경계 포함 여부 제어
    """
    m1 = re.search(re.escape(start), text, flags)
    if not m1:
        return ""

    s = m1.start() if include_start else m1.end()

    if end is None:
        return text[s:]

    m2 = re.search(re.escape(end), text[m1.end() :], flags)
    if not m2:
        # end가 없으면 start부터 끝까지
        return text[s:]

    e = (m1.end() + m2.end()) if include_end else (m1.end() + m2.start())
    return text[s:e]


# 첫 문자열 포함 마지막 문자열 미포함
def slice_including_to_before(
    text: str,
    start: str,
    end: Optional[str],
    *,
    start_occurrence: int = 1,
    end_occurrence: int = 1,
    not_found: str = "",
    ) -> str:
    """
    text에서 start(포함) ~ end(직전) 구간 반환.
    - start_occurrence: start가 여러 번 나오면 몇 번째 것을 기준으로 할지 (1=첫 번째)
    - end_occurrence: end가 여러 번 나오면 몇 번째 것을 기준으로 할지 (1=첫 번째)
    - end가 None이면 start부터 끝까지
    - start를 못 찾으면 not_found 반환
    """
    # start 찾기 (n번째 occurrence)
    s = -1
    pos = 0
    for _ in range(start_occurrence):
        s = text.find(start, pos)
        if s == -1:
            return not_found
        pos = s + len(start)

    if end is None:
        return text[s:]

    # end 찾기 (start 뒤에서 n번째 occurrence)
    e = -1
    pos = pos  # start 다음 위치부터 탐색
    for _ in range(end_occurrence):
        e = text.find(end, pos)
        if e == -1:
            # end가 없으면 start부터 끝까지로 처리
            return text[s:]
        pos = e + len(end)

    return text[s:e]

# 첫 문자열 포함 마지막 문자열 포함
def slice_include_start_include_end(
    text: str,
    start: str,
    end: Optional[str] = None,
    *,
    flags: int = 0
    ) -> str:
    """
    text에서 start(포함) ~ end(포함) 구간을 반환.
    - end가 None이면 start부터 끝까지 반환
    - start를 못 찾으면 "" 반환
    - end를 못 찾으면 start부터 끝까지 반환
    """
    m1 = re.search(re.escape(start), text, flags)
    if not m1:
        return ""

    s = m1.start()  # start 포함

    if end is None:
        return text[s:]

    # start 이후에서 end 찾기
    m2 = re.search(re.escape(end), text[m1.end():], flags)
    if not m2:
        return text[s:]

    # end 포함하려면 end의 끝까지
    e = m1.end() + m2.end()
    return text[s:e]

#첫 문자열 포함 or 미포함, 마지막 문자열 포함 or 미포함 함수
def slice_between_occurrences(
    text: str,
    start: str,
    end: Optional[str],
    *,
    start_occurrence: int = 1,
    end_occurrence: int = 1,
    include_start: bool = True,
    include_end: bool = False,
    not_found: str = "",
    ) -> str:
    """
    text에서 start ~ end 구간을 잘라 반환 (occurrence 지원).

    - start_occurrence: start가 여러 번 나오면 몇 번째 start를 기준으로 할지 (1=첫 번째)
    - end_occurrence: start "이후"에 나오는 end 중 몇 번째 end를 기준으로 할지 (1=첫 번째)
    - include_start/include_end: 경계 문자열 포함 여부
    - end가 None이면 start 기준으로 끝까지
    - start를 못 찾으면 not_found 반환
    - end를 못 찾으면 start부터 끝까지 반환(기존 동작 유지)
    """

    if start_occurrence < 1 or end_occurrence < 1:
        raise ValueError("start_occurrence와 end_occurrence는 1 이상의 정수여야 합니다.")

    # 1) start 찾기 (n번째 occurrence)
    s = -1
    pos = 0
    for _ in range(start_occurrence):
        s = text.find(start, pos)
        if s == -1:
            return not_found
        pos = s + len(start)  # 다음 start 탐색은 이 뒤부터

    # start 포함/미포함 적용
    start_idx = s if include_start else s + len(start)

    # 2) end가 None이면 start 기준으로 끝까지
    if end is None:
        return text[start_idx:]

    # 3) end 찾기 (start 뒤에서 n번째 occurrence)
    e = -1
    search_pos = pos  # start 다음 위치부터 탐색
    for _ in range(end_occurrence):
        e = text.find(end, search_pos)
        if e == -1:
            # end가 없으면 start부터 끝까지
            return text[start_idx:]
        search_pos = e + len(end)

    # end 포함/미포함 적용
    end_idx = e + len(end) if include_end else e

    return text[start_idx:end_idx]


# 역주행을 하며 마지막 문자열 미포함, 첫 문자열 포함
def slice_from_last_start_before_end(
    text: str,
    start_marker: str,
    end_marker: str,
    *,
    include_start: bool = True,
    include_end: bool = False,
    use_last_end: bool = True,  # end_marker가 여러 개면 마지막 것을 기준
    not_found: str = "",
    ) -> str:
    """
    end_marker 위치에서 왼쪽으로 역주행하며 가장 가까운 start_marker를 찾아,
    start_marker ~ end_marker 사이를 잘라 반환.

    기본 동작:
    - start_marker 포함 (include_start=True)
    - end_marker 미포함, 직전까지 (include_end=False)
    - end_marker는 마지막 등장(use_last_end=True)을 기준
    """
    # 1) end_marker 위치 찾기
    end_pos = text.rfind(end_marker) if use_last_end else text.find(end_marker)
    if end_pos == -1:
        return not_found

    # 2) end_marker "앞부분"에서 start_marker를 뒤에서 찾기(=역주행 효과)
    start_pos = text.rfind(start_marker, 0, end_pos)
    if start_pos == -1:
        return not_found

    # 3) 포함/미포함 옵션 반영
    s = start_pos if include_start else start_pos + len(start_marker)
    e = end_pos + len(end_marker) if include_end else end_pos

    return text[s:e]


# 역주행을 하며 마지막 문자열 미포함, 첫 문자열 포함 인데, 첫 문자열은 리스트 / 튜플
def slice_from_last_start_before_end_any(
    text: str,
    start_markers: list[str],  # 리스트/튜플 OK
    end_marker: str,
    *,
    include_start: bool = True,
    include_end: bool = False,
    use_last_end: bool = True,
    not_found: str = "",
    ) -> str:
    # 1) end_marker 위치
    end_pos = text.rfind(end_marker) if use_last_end else text.find(end_marker)
    if end_pos == -1:
        return not_found

    # 2) end_marker 앞에서 start 후보들 중 "가장 뒤에 있는 것" 선택
    best_start_pos = -1
    best_start_len = 0

    for sm in start_markers:
        pos = text.rfind(sm, 0, end_pos)
        if pos > best_start_pos:
            best_start_pos = pos
            best_start_len = len(sm)

    if best_start_pos == -1:
        return not_found

    # 3) 포함/미포함 적용
    s = best_start_pos if include_start else best_start_pos + best_start_len
    e = end_pos + len(end_marker) if include_end else end_pos
    return text[s:e]


# 역주행을 하며 마지막 문자열 미포함, 첫 문자열 포함 인데 정규표현식 사용
def slice_from_last_start_before_end_regex(
    text: str,
    start_pat: str,  # regex
    end_lit: str,  # literal
    *,
    include_start: bool = True,
    include_end: bool = False,
    use_last_end: bool = True,
    flags: int = re.S,
    not_found: str = "",
    ) -> str:
    end_pos = text.rfind(end_lit) if use_last_end else text.find(end_lit)
    if end_pos == -1:
        return not_found

    # end_pos 앞쪽에서 start_pat의 "마지막 매치" 찾기
    prefix = text[:end_pos]
    last = None
    for m in re.finditer(start_pat, prefix, flags):
        last = m

    if last is None:
        return not_found

    s = last.start() if include_start else last.end()
    e = end_pos + len(end_lit) if include_end else end_pos
    return text[s:e]


# 역주행을 하며 마지막 문자열 포함, 첫 문자열 미포함
def slice_after_start_to_including_end_reverse(
    text: str,
    start_marker: str,
    end_marker: str,
    *,
    use_last_end: bool = True,
    not_found: str = "",
    ) -> str:
    """
    end_marker(기준)를 잡고, 그 앞에서 가장 가까운 start_marker를 '역주행'으로 찾아,
    start_marker는 제외(미포함)하고 end_marker는 포함하여 반환한다.

    반환 구간:
      (start_marker의 끝)  ~  (end_marker의 끝)

    - use_last_end=True이면 end_marker가 여러 번 나와도 '마지막 end_marker'를 기준으로 함
      False면 첫 번째 end_marker를 기준으로 함
    """
    # 1) end_marker 위치 잡기
    end_pos = text.rfind(end_marker) if use_last_end else text.find(end_marker)
    if end_pos == -1:
        return not_found

    end_end = end_pos + len(end_marker)  # end_marker 포함이므로 끝 위치는 여기

    # 2) end_marker 앞쪽에서 start_marker를 뒤에서부터(가장 가까운 것) 찾기
    start_pos = text.rfind(start_marker, 0, end_pos)
    if start_pos == -1:
        return not_found

    start_end = start_pos + len(start_marker)  # start_marker 미포함이므로 여기서 시작

    # 3) 구간 반환
    return text[start_end:end_end]


# 기준 문자열과 같은 단어들만 추출
def _normalize_token(tok: str) -> str:
    """
    OCR 흔들림을 조금 견디게 토큰 정규화.
    - 양끝 특수문자 제거
    - 공백류 제거는 token 단계에선 필요 없음
    - 하이픈은 유지(496-10 같은 지번에 중요)
    """
    tok = tok.strip()
    # 토큰 양끝의 불필요한 문장부호 제거 (하이픈은 유지해야 하므로 제외)
    tok = re.sub(r"^[\s,.:;(){}\[\]<>\"'`]+|[\s,.:;(){}\[\]<>\"'`]+$", "", tok)
    return tok


def extract_reference_subsequence(
    source: str, reference: str, *, require_exact: bool = True
    ) -> Tuple[bool, str]:
    """
    source에서 reference 토큰들을 '순서대로' 찾아서 뽑아냄.
    - 성공: (True, reference를 정규화해 조합한 문자열)
    - 실패: (False, 실패 이유)
    """
    # 줄바꿈/탭 등 공백 정리
    source_clean = re.sub(r"\s+", " ", source).strip()
    ref_clean = re.sub(r"\s+", " ", reference).strip()

    source_tokens = [
        _normalize_token(t) for t in source_clean.split(" ") if _normalize_token(t)
    ]
    ref_tokens = [
        _normalize_token(t) for t in ref_clean.split(" ") if _normalize_token(t)
    ]

    if not ref_tokens:
        return False, "reference가 비어있음"

    # 투 포인터로 subsequence 매칭
    j = 0
    for tok in source_tokens:
        if tok == ref_tokens[j]:
            j += 1
            if j == len(ref_tokens):
                break

    if j != len(ref_tokens):
        return False, f"reference 토큰을 전부 찾지 못함 (진행 {j}/{len(ref_tokens)})"

    # 성공 시: reference와 '똑같이' 만들고 싶다면 reference 기반으로 반환
    result = " ".join(ref_tokens)

    if require_exact:
        # 완전 동일(정규화 기준) 확인
        if result != " ".join(ref_tokens):
            return False, "정규화 후에도 동일 문자열 구성 실패"
        return True, result

    return True, result


# 기준 문자열과 다른 단어들만 추출
def remove_reference_subsequence(
    source: str, reference: str, *, fail_if_not_found: bool = True
    ) -> Tuple[bool, str]:
    """
    source에서 reference 토큰들을 '순서대로' 매칭해 제거하고,
    남은 토큰들을 공백으로 합쳐 반환.

    - fail_if_not_found=True이면 reference 토큰을 전부 못 찾으면 실패 처리
    - False이면 찾은 것만 제거하고 남은 것 반환
    """
    source_clean = re.sub(r"\s+", " ", source).strip()
    ref_clean = re.sub(r"\s+", " ", reference).strip()

    source_tokens: List[str] = [
        _normalize_token(t) for t in source_clean.split(" ") if _normalize_token(t)
    ]
    ref_tokens: List[str] = [
        _normalize_token(t) for t in ref_clean.split(" ") if _normalize_token(t)
    ]

    if not ref_tokens:
        return False, "reference가 비어있음"

    kept = []
    j = 0  # ref_tokens 포인터

    for tok in source_tokens:
        if j < len(ref_tokens) and tok == ref_tokens[j]:
            # 매칭된 reference 토큰은 제거(keep 안 함)
            j += 1
        else:
            kept.append(tok)

    if fail_if_not_found and j != len(ref_tokens):
        return False, f"reference 토큰을 전부 찾지 못함 (진행 {j}/{len(ref_tokens)})"

    return True, " ".join(kept)


# ==========================================
# 0 - 1. [유틸] PDF 쪼개기 함수
# ==========================================
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
def call_naver_ocr(file_bytes, file_ext, api_url, secret_key):
    """네이버 OCR을 호출해서 JSON 결과를 받아옵니다."""
    request_json = {
        "images": [{"format": file_ext, "name": "demo"}],
        "requestId": str(uuid.uuid4()),
        "version": "V2",
        "timestamp": int(round(time.time() * 1000)),
    }

    payload = {"message": json.dumps(request_json)}
    headers = {"X-OCR-SECRET": secret_key}

    content_type = "application/pdf" if file_ext == "pdf" else "image/jpeg"
    files = {"file": (f"upload.{file_ext}", file_bytes, content_type)}

    try:
        r = requests.post(
            api_url, headers=headers, data=payload, files=files, timeout=60
        )

        return {
            "ok": (r.status_code == 200),
            "status_code": r.status_code,
            "text": r.text[:2000],
            "json": (
                r.json()
                if "application/json" in r.headers.get("Content-Type", "")
                else None
            ),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ==========================================
# 2. [전처리] JSON -> 줄글 텍스트 변환
# ==========================================
def json_to_text_lines(ocr_json, line_y_threshold=15):
    """
    OCR 결과(JSON)의 모든 페이지(images)를 순서대로 텍스트로 합칩니다.
    각 페이지는 '위->아래, 좌->우' 정렬 후 줄 단위로 재구성합니다.
    """
    if not ocr_json or "images" not in ocr_json:
        return ""

    pages_text = []

    for page_idx, img in enumerate(ocr_json["images"], start=1):
        fields = img.get("fields", [])
        extracted_data = []

        for field in fields:
            text = field.get("inferText", "")
            verts = field.get("boundingPoly", {}).get("vertices", [])
            if not verts:
                continue
            x = verts[0].get("x", 0)
            y = verts[0].get("y", 0)
            extracted_data.append({"text": text, "x": x, "y": y})

        extracted_data.sort(key=lambda k: k["y"])

        full_text = ""
        if extracted_data:
            current_line = []
            last_y = extracted_data[0]["y"]

            for item in extracted_data:
                if abs(item["y"] - last_y) > line_y_threshold:
                    current_line.sort(key=lambda k: k["x"])
                    full_text += (
                        " ".join([d["text"] for d in current_line]).strip() + "\n"
                    )
                    current_line = []

                current_line.append(item)
                last_y = item["y"]

            if current_line:
                current_line.sort(key=lambda k: k["x"])
                full_text += " ".join([d["text"] for d in current_line]).strip()

        pages_text.append(f"\n===== PAGE {page_idx} =====\n{full_text}".strip())

    return "\n".join(pages_text).strip()


# ==========================================
# 3. [전처리] pdf의 카테고리 추출 함수
# ==========================================
def extract_pdf_category(text: str) -> str:
    """
    PDF 문서의 카테고리를 추출합니다.
    """
    if (
        ("토지이용계획확인서" in text)
        and ("등기사항전부증명서" in text)
        and ("토지 대장" in text)
    ):

        return "토지이용계획확인서_토지등기_토지대장"
    return "기타"


# ==========================================
# 4 - 0. [핵심] 절대 규칙(Rule)으로 데이터 뽑기위한 함수 할당하는 함수 ⚡
# ==========================================
def extract_data_by_rules(text, pdf_category):
    """
    텍스트 덩어리에서 정규표현식(Regex)을 이용해 핵심 데이터를 추출합니다.
    """
    if pdf_category == "토지이용계획확인서_토지등기_토지대장":
        return extract_land_document_data(text)


# ==========================================
# 4 - 1. 토지이용계획확인서_토지등기_토지대장 문서용 데이터 추출 함수
# ==========================================
def extract_land_document_data(text):
    """
    토지 관련 문서에서 데이터를 추출합니다.
    """
    data = {}

    # --- 규칙 0: 문서 범위 나누기 ---
    # 토지이용계획확인서
    land_use_plan_section = slice_between(text, "문서확인번호", "등기사항전부증명서")
    # 등기사항전부증명서
    land_registry_section = slice_between(text, "등기사항전부증명서", "토지 대장")
    # 주요 등기사항 요약
    land_registry_summary_section = slice_between(text, "주요 등기사항 요약", "토지 대장")
    # 토지 대장
    land_register_section = slice_between(text, "토지 대장", "문서확인번호")

    # === 표제부에서 필요한 정보 추출 ===
    # [토지] 추출
    land_address_in_registry_1 = slice_including_to_before(land_registry_section, "[토지]", "표제부")
    land_address_in_registry_1 = land_address_in_registry_1.replace("[토지]", "").strip()
    if land_address_in_registry_1:
        data["[토지]"] = land_address_in_registry_1
    else:
        data["[토지]"] = "찾지 못함"

    # 소재지번, 지목, 면적을 추출하기위한 범위 설정
    section_for_header_1 = slice_from_last_start_before_end_regex(
        land_registry_section, r"\n\d\s", "갑 구"
    )

    # 면적 구하기
    m2 = re.search(r"(\d+(?:,\d+)*(?:\.\d+)?)\s*m2", section_for_header_1, re.I)
    land_area_in_registry = (m2.group(1).replace(",", "") + "m2") if m2 else ""

    # 지목 추출
    m = re.search(
        r"([가-힣]+)\s*\d+(?:,\d+)*(?:\.\d+)?\s*m2", section_for_header_1, re.I
    )
    land_category_in_registry = m.group(1) if m else ""

    # 소재 지번 추출
    true_or_false_of_match_1, land_address_in_registry_2 = (
        extract_reference_subsequence(section_for_header_1, land_address_in_registry_1)
    )
    if land_address_in_registry_2:
        data["소재지번(토지)"] = land_address_in_registry_2
    else:
        data["소재지번(토지)"] = "찾지 못함"
    # 토지 & 소재지번 매칭 여부
    if true_or_false_of_match_1 == False:
        data["토지 & 소재지번 매칭 여부"] = "X"
    else:
        data["토지 & 소재지번 매칭 여부"] = "O"

    # 지목 추출
    if land_category_in_registry:
        data["지목(토지)"] = land_category_in_registry
    else:
        data["지목(토지)"] = "찾지 못함"

    # 면적 추출
    if land_area_in_registry:
        data["면적(토지)"] = land_area_in_registry
    else:
        data["면적(토지)"] = "찾지 못함"

    # -------------------------------------
    # 갑 구 (소유권에 관한 사항)
    # -------------------------------------
    land_registry_section_gabgu = slice_include_start_include_end(land_registry_section, "갑 구", "을 구")

    # 갑구에서 마지막 칸 떼어내기
    land_registry_section_gabgu_last = slice_from_last_start_before_end_regex(
        land_registry_section_gabgu, r"\n\d\s", "을 구"
    )

    # 갑구에서 등기목적 추출
    land_registry_section_gabgu_last_purpose = slice_including_to_before(
        land_registry_section_gabgu_last, " ", " "
    )

    if land_registry_section_gabgu_last_purpose:
        data["토지_등기_갑구_등기목적"] = land_registry_section_gabgu_last_purpose.strip()
    else:
        data["토지_등기_갑구_등기목적"] = "찾지 못함"
    

    # 갑구에서 접수일자 추출
    land_registry_section_gabgu_last_date_1 = slice_between_occurrences(
        land_registry_section_gabgu_last,
        land_registry_section_gabgu_last_purpose + " ",
        " ",
        include_start=False,
        include_end=False,
    )

    # 접수의 호 추출 하기위한 특수 범위 설정
    section_for_standard_1 = slice_between_occurrences(
        land_registry_section_gabgu_last, land_registry_section_gabgu_last_date_1, "\n",
        include_start=False,
        include_end=False,
    )

    # 접수의 호 추출
    land_registry_section_gabgu_last_date_1_ho = slice_between_occurrences(
        land_registry_section_gabgu_last,
        section_for_standard_1 + "\n",
        " ",
        include_start=False,
        include_end=False,
    )

    # 접수일자 + 호 합치기
    land_registry_section_gabgu_last_jupsu = (
        land_registry_section_gabgu_last_date_1 
        + " " + land_registry_section_gabgu_last_date_1_ho
    )

    if land_registry_section_gabgu_last_jupsu:
        data["토지_등기_갑구_접수"] = land_registry_section_gabgu_last_jupsu.strip()
    else:
        data["토지_등기_갑구_접수"] = "찾지 못함"

    # 갑구에서 등기원인 추출
    land_registry_section_gabgu_last_cause = slice_including_to_before(
        land_registry_section_gabgu_last,
        land_registry_section_gabgu_last_date_1 + " ",
        " ",
    )
    if land_registry_section_gabgu_last_cause:
        data["토지_등기_갑구_등기원인"] = (
            land_registry_section_gabgu_last_cause + " " + "매매"
        )
    else:
        data["토지_등기_갑구_등기원인"] = "찾지 못함"

    # 갑구에서 권리자 및 기타사항 추출
    ok_true_or_false_of_match_2, land_registry_section_gabgu_last_right_holder = (
        remove_reference_subsequence(
            land_registry_section_gabgu_last,
            land_registry_section_gabgu_last_purpose
            + land_registry_section_gabgu_last_date_1
            + land_registry_section_gabgu_last_date_1_ho
            + land_registry_section_gabgu_last_cause
            + "매매",
        )
    )

    if ok_true_or_false_of_match_2:
        data["토지_등기_갑구_권리자및기타사항"] = (
            land_registry_section_gabgu_last_right_holder.strip()
        )
    else:
        data["토지_등기_갑구_권리자및기타사항"] = "찾지 못함"

    # 갑구에서 소유자 찾기
    land_registry_section_gabgu_owner = re.search(
        r"소유자\s*([가-힣]{2,4})\s*\d{6}-\*{7}", land_registry_section_gabgu_last
    )
    if land_registry_section_gabgu_owner:
        data["토지_등기_갑구_최종 소유자"] = land_registry_section_gabgu_owner.group(1)
    else:
        data["토지_등기_갑구_최종 소유자"] = "찾지 못함"

    # 주요 등기사항 요약에서 최종 소유자 찾기
    land_registry_summary_section_owner = slice_including_to_before(
        land_registry_summary_section, "순위번호", " (소유자)"
    )
    if land_registry_summary_section_owner:
        data["토지_등기_요약_최종 소유자"] = land_registry_summary_section_owner.strip()
    else:
        data["토지_등기_요약_최종 소유자"] = "찾지 못함"

    # 최종 소유자 일치 여부
    if land_registry_summary_section_owner == data["토지_등기_갑구_최종 소유자"]:
        data["토지_등기_최종 소유자 일치 여부"] = "O"
    else:
        data["토지_등기_최종 소유자 일치 여부"] = "X"

    return data


# main 함수
def main():

    # 페이지 상단 및 설정
    st.set_page_config(
        page_title="문서 비서",
        page_icon="📄",  # 이모지 유니코드: U+1F4C4
        layout="wide",
    )

    # 제목
    st.title("문서 비서📄 dev")

    # 개발 단계
    st.subheader("토지의 소재지를 출력하는 프로토타입 v0.4")

    # 서비스 설명
    st.markdown(
        """
        문서 비서는 다양한 형식의 문서를 텍스트로 변환하고, 
        사용자가 원하는 핵심 데이터를 추출하는 도구입니다.
        """
    )

    # 비밀번호(임시)
    password = st.text_input("비밀번호를 입력하세요", type="password")
    if password != "alohomora":
        st.warning("비밀번호가 올바르지 않습니다.")
        return

    st.success("환영합니다! 문서 비서를 시작합니다.")

    # 사이드바 API 설정
    with st.sidebar:
        try:
            api_url = st.secrets["NAVER_API_URL"]
            secret_key = st.secrets["NAVER_SECRET_KEY"]
        except KeyError:
            api_url = st.text_input("API URL")
            secret_key = st.text_input("Secret Key", type="password")

    # 파일 업로드
    uploaded_file = st.file_uploader(
        "문서파일을 업로드하세요", type=["pdf"], key="uploader_pdf"
    )
    if uploaded_file is not None:
        st.success("파일이 업로드되었습니다.")

    # 업로드된 파일 해시 계산 (파일이 바뀌면 결과 초기화용)
    file_hash = None
    file_bytes = None
    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        # 파일이 바뀌면 이전 결과 자동 초기화
        if st.session_state.get("file_hash") != file_hash:
            st.session_state.pop("raw_text", None)
            st.session_state.pop("extracted_data", None)
            st.session_state.pop("excel_bytes", None)
            st.session_state["file_hash"] = file_hash

    # 버튼은 딱 1번만 렌더링
    clicked = st.button(
        "🔍 데이터 추출 시작",
        key="extract_btn",
        disabled=(uploaded_file is None),
    )

    if clicked:
        if not api_url:
            st.error("API URL 확인 필요")
            st.stop()
        if not secret_key:
            st.error("Secret Key 확인 필요")
            st.stop()

        with st.spinner("OCR 및 데이터 추출 중..."):
            progress_bar = st.progress(0)
            status = st.empty()

            def progress_cb(i, total, start_p, end_p):
                pct = int(i / total * 100)
                progress_bar.progress(pct)
                status.write(
                    f"📄 OCR 진행: {i}/{total} 묶음 (페이지 {start_p}~{end_p})"
                )

            try:
                raw_text, extracted_data, excel_bytes = process_pdf(
                    file_bytes, api_url, secret_key, progress_cb=progress_cb
                )
            except Exception as e:
                st.error(str(e))
                st.stop()

            progress_bar.progress(100)
            status.write("✅ OCR 완료")

        st.session_state["raw_text"] = raw_text
        st.session_state["extracted_data"] = extracted_data
        st.session_state["excel_bytes"] = excel_bytes

    # ✅ 결과는 session_state에 있으면 언제든 표시 (rerun돼도 유지)
    if st.session_state.get("extracted_data") is not None:
        extracted_data = st.session_state["extracted_data"]
        raw_text = st.session_state["raw_text"]
        excel_bytes = st.session_state["excel_bytes"]

        st.divider()
        col1, col2 = st.columns([1, 1])

        with col1:
            st.subheader("✅ 추출 결과 (Excel)")
            df = pd.DataFrame([extracted_data])
            st.dataframe(df.T, use_container_width=True)

            st.download_button(
                label="📥 엑셀 파일 다운로드",
                data=excel_bytes,
                file_name=f"규칙추출_{uploaded_file.name if uploaded_file else 'result'}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_excel_btn",
            )

        with col2:
            st.subheader("📄 AI가 읽은 원본 텍스트")
            st.text_area("OCR Raw Text", raw_text, height=400, key="raw_text_area")
    else:
        st.info("파일 업로드 후 '데이터 추출 시작'을 누르면 결과가 여기에 유지됩니다.")


# 실행
if __name__ == "__main__":
    main()
