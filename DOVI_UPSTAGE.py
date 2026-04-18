# DOVI (Upstage version)
# version 0.0.0

import hashlib
import hmac
import io
import json
import os
import re
from html import unescape
from html.parser import HTMLParser

import pandas as pd
import requests
import streamlit as st

#------------------------------
# 비밀번호
#------------------------------
APP_PASSWORD = "alohomora"

#------------------------------
# Upstage API 설정
#------------------------------
UPSTAGE_API_URL = "https://api.upstage.ai/v1/document-digitization"

#------------------------------
# 추출 대상 표 구분
#------------------------------
TARGET_SECTIONS = ("표제부", "갑구", "을구")
SECTION_LABELS = {
    "표제부": "표제부",
    "갑구": "갑 구",
    "을구": "을 구",
}
SECTION_PATTERNS = {
    "표제부": re.compile(r"표\s*제\s*부"),
    "갑구": re.compile(r"갑\s*구"),
    "을구": re.compile(r"을\s*구"),
}
GENERIC_COLUMN_PATTERN = re.compile(r"^col_\d+$")
HEADER_ROW_TOKENS = {
    "순위번호",
    "등기목적",
    "접수",
    "등기원인",
    "권리자및기타사항",
    "고유번호",
    "표시번호",
    "등기명의인",
    "주민등록번호",
    "최종지분",
    "주소",
}


#------------------------------
# HTML 표 파서
#------------------------------
class SimpleHTMLTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables = []
        self.current_table = None
        self.current_row = None
        self.current_row_has_header = False
        self.current_cell_parts = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()

        if tag == "table":
            self.current_table = []
            return

        if self.current_table is None:
            return

        if tag == "tr":
            self.current_row = []
            self.current_row_has_header = False
            return

        if tag in ("td", "th") and self.current_row is not None:
            self.current_cell_parts = []
            if tag == "th":
                self.current_row_has_header = True
            return

        if tag == "br" and self.current_cell_parts is not None:
            self.current_cell_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if tag in ("td", "th") and self.current_cell_parts is not None:
            cell_text = normalize_space(unescape("".join(self.current_cell_parts)))
            self.current_row.append(cell_text)
            self.current_cell_parts = None
            return

        if tag == "tr" and self.current_row is not None and self.current_table is not None:
            self.current_table.append(
                {
                    "cells": self.current_row,
                    "is_header": self.current_row_has_header,
                }
            )
            self.current_row = None
            self.current_row_has_header = False
            return

        if tag == "table" and self.current_table is not None:
            self.tables.append(self.current_table)
            self.current_table = None

    def handle_data(self, data: str) -> None:
        if self.current_cell_parts is not None:
            self.current_cell_parts.append(data)


def require_password() -> None:
    if st.session_state.get("password_ok", False):
        return

    st.title("DOVI (Upstage version)")
    st.write("비밀번호를 입력해주세요.")

    with st.form("password_form", clear_on_submit=True):
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Continue")

    if submitted:
        if hmac.compare_digest(password, APP_PASSWORD):
            st.session_state["password_ok"] = True
            st.rerun()
        else:
            st.error("비밀번호가 올바르지 않습니다.")

    st.stop()


#------------------------------
# Upstage OCR 호출
#------------------------------
def call_upstage_document_parse(
    file_name: str,
    file_bytes: bytes,
    api_key: str,
) -> dict:
    headers = {"Authorization": f"Bearer {api_key}"}
    files = {"document": (file_name, file_bytes, "application/pdf")}
    data = {
        "ocr": "force",
        "coordinates": json.dumps(True),
        "chart_recognition": json.dumps(True),
        "output_formats": json.dumps(["markdown", "html", "text"]),
        "model": "document-parse",
    }

    response = requests.post(
        UPSTAGE_API_URL,
        headers=headers,
        files=files,
        data=data,
        timeout=300,
    )

    try:
        response_json = response.json()
    except ValueError:
        response.raise_for_status()
        raise RuntimeError("Upstage 응답을 JSON으로 읽지 못했습니다.")

    if not response.ok:
        error_message = response_json.get("message") or response.text
        raise RuntimeError(
            f"Upstage OCR 요청이 실패했습니다. "
            f"(status={response.status_code}) {error_message}"
        )

    return response_json


#------------------------------
# 문자열 정리
#------------------------------
def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def normalize_compare_text(text: str) -> str:
    text = normalize_space(str(text))
    return re.sub(r"[\W_]+", "", text).lower()


def strip_html_tags(html_text: str) -> str:
    if not html_text:
        return ""

    html_text = re.sub(r"<br\s*/?>", "\n", html_text, flags=re.I)
    html_text = re.sub(r"</(p|div|tr|li|h\d|table)>", "\n", html_text, flags=re.I)
    html_text = re.sub(r"<[^>]+>", " ", html_text)
    return normalize_space(unescape(html_text))


#------------------------------
# 표 구분 감지
#------------------------------
def detect_section_from_text(text: str) -> str | None:
    for section_name in TARGET_SECTIONS:
        if SECTION_PATTERNS[section_name].search(text):
            return section_name
    return None


def get_element_search_text(element: dict) -> str:
    content = element.get("content", {})
    parts = [
        element.get("category", ""),
        content.get("text", ""),
        content.get("markdown", ""),
        strip_html_tags(content.get("html", "")),
    ]
    return "\n".join(part for part in parts if part).strip()


def is_table_element(element: dict) -> bool:
    category = (element.get("category") or "").lower()
    content = element.get("content", {})
    html_text = content.get("html", "") or ""
    markdown_text = content.get("markdown", "") or ""

    if category == "table":
        return True

    if "<table" in html_text.lower():
        return True

    return has_markdown_table(markdown_text)


#------------------------------
# HTML / Markdown 표 파싱
#------------------------------
def make_unique_columns(columns: list[str]) -> list[str]:
    unique_columns = []
    seen = {}

    for index, column in enumerate(columns, start=1):
        column = normalize_space(column)
        if not column:
            column = f"col_{index}"

        count = seen.get(column, 0) + 1
        seen[column] = count

        if count > 1:
            column = f"{column}_{count}"

        unique_columns.append(column)

    return unique_columns


def rows_to_dataframe(rows: list[dict]) -> pd.DataFrame:
    valid_rows = [row for row in rows if any(normalize_space(cell) for cell in row["cells"])]
    if not valid_rows:
        return pd.DataFrame()

    max_columns = max(len(row["cells"]) for row in valid_rows)
    normalized_rows = [
        row["cells"] + [""] * (max_columns - len(row["cells"]))
        for row in valid_rows
    ]

    header_index = next(
        (index for index, row in enumerate(valid_rows) if row["is_header"]),
        None,
    )

    if header_index is not None:
        columns = make_unique_columns(normalized_rows[header_index])
        data_rows = (
            normalized_rows[:header_index] + normalized_rows[header_index + 1 :]
        )
    else:
        columns = [f"col_{index}" for index in range(1, max_columns + 1)]
        data_rows = normalized_rows

    return pd.DataFrame(data_rows, columns=columns)


def parse_html_tables(html_text: str) -> list[pd.DataFrame]:
    if "<table" not in (html_text or "").lower():
        return []

    parser = SimpleHTMLTableParser()
    parser.feed(html_text)

    dataframes = []
    for table_rows in parser.tables:
        dataframe = rows_to_dataframe(table_rows)
        if not dataframe.empty or len(dataframe.columns) > 0:
            dataframes.append(dataframe)

    return dataframes


def is_markdown_separator_row(cells: list[str]) -> bool:
    if not cells:
        return False

    for cell in cells:
        token = cell.replace(" ", "")
        if not re.fullmatch(r":?-{3,}:?", token):
            return False

    return True


def split_markdown_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [normalize_space(cell) for cell in line.split("|")]


def has_markdown_table(markdown_text: str) -> bool:
    if not markdown_text:
        return False

    table_like_lines = [
        line for line in markdown_text.splitlines() if line.count("|") >= 2
    ]
    return len(table_like_lines) >= 2


def parse_markdown_table_block(block_lines: list[str]) -> pd.DataFrame:
    rows = [split_markdown_row(line) for line in block_lines if line.strip()]
    if not rows:
        return pd.DataFrame()

    max_columns = max(len(row) for row in rows)
    rows = [row + [""] * (max_columns - len(row)) for row in rows]

    if len(rows) >= 2 and is_markdown_separator_row(rows[1]):
        columns = make_unique_columns(rows[0])
        data_rows = rows[2:]
    else:
        columns = [f"col_{index}" for index in range(1, max_columns + 1)]
        data_rows = rows

    return pd.DataFrame(data_rows, columns=columns)


def parse_markdown_tables(markdown_text: str) -> list[pd.DataFrame]:
    dataframes = []
    current_block = []

    for line in markdown_text.splitlines():
        if line.count("|") >= 2:
            current_block.append(line)
        else:
            if len(current_block) >= 2:
                dataframe = parse_markdown_table_block(current_block)
                if not dataframe.empty or len(dataframe.columns) > 0:
                    dataframes.append(dataframe)
            current_block = []

    if len(current_block) >= 2:
        dataframe = parse_markdown_table_block(current_block)
        if not dataframe.empty or len(dataframe.columns) > 0:
            dataframes.append(dataframe)

    return dataframes


def extract_table_dataframes(element: dict) -> list[pd.DataFrame]:
    content = element.get("content", {})
    html_text = content.get("html", "") or ""
    markdown_text = content.get("markdown", "") or ""

    html_tables = parse_html_tables(html_text)
    if html_tables:
        return html_tables

    return parse_markdown_tables(markdown_text)


#------------------------------
# 표 정리 / 병합
#------------------------------
def clean_cell_value(value) -> str:
    if pd.isna(value):
        return ""

    text = str(value).replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    if text.lower() == "nan":
        return ""

    return text


def clean_table_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe is None:
        return pd.DataFrame()

    dataframe = dataframe.copy()
    dataframe.columns = make_unique_columns([str(column) for column in dataframe.columns])

    for column in dataframe.columns:
        dataframe[column] = dataframe[column].map(clean_cell_value)

    if len(dataframe.columns) == 0:
        return dataframe

    non_empty_rows = dataframe.apply(
        lambda row: any(normalize_compare_text(value) for value in row.tolist()),
        axis=1,
    )
    dataframe = dataframe.loc[non_empty_rows].reset_index(drop=True)

    non_empty_columns = [
        column
        for column in dataframe.columns
        if normalize_compare_text(column)
        or dataframe[column].map(normalize_compare_text).any()
    ]
    dataframe = dataframe[non_empty_columns]

    return dataframe


def row_cells_to_text(cells: list[str]) -> str:
    return " ".join(cell for cell in cells if normalize_space(cell)).strip()


def is_generic_columns(columns: list[str]) -> bool:
    if not columns:
        return False
    return all(GENERIC_COLUMN_PATTERN.fullmatch(str(column)) for column in columns)


def is_header_row_values(cells: list[str]) -> bool:
    normalized_cells = [
        normalize_compare_text(cell)
        for cell in cells
        if normalize_compare_text(cell)
    ]
    if len(normalized_cells) < 2:
        return False

    token_matches = sum(1 for cell in normalized_cells if cell in HEADER_ROW_TOKENS)
    return token_matches >= 2


def promote_first_row_to_header_if_needed(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe

    if not is_generic_columns(list(dataframe.columns)):
        return dataframe

    first_row = [clean_cell_value(value) for value in dataframe.iloc[0].tolist()]
    if not is_header_row_values(first_row):
        return dataframe

    promoted_dataframe = dataframe.iloc[1:].reset_index(drop=True).copy()
    promoted_dataframe.columns = make_unique_columns(first_row)
    return promoted_dataframe


def ensure_minimum_columns(dataframe: pd.DataFrame, minimum_columns: int = 5) -> pd.DataFrame:
    dataframe = dataframe.copy()

    while len(dataframe.columns) < minimum_columns:
        next_index = len(dataframe.columns) + 1
        column_name = f"col_{next_index}"
        while column_name in dataframe.columns:
            next_index += 1
            column_name = f"col_{next_index}"
        dataframe[column_name] = ""

    return dataframe


def extract_leading_number(text: str) -> int | None:
    match = re.match(r"^\s*(\d+)", text or "")
    if not match:
        return None
    return int(match.group(1))


def append_with_blank_line(base_text: str, extra_text: str) -> str:
    base_text = clean_cell_value(base_text)
    extra_text = clean_cell_value(extra_text)

    if not extra_text:
        return base_text
    if not base_text:
        return extra_text
    return f"{base_text}\n\n{extra_text}"


def row_to_continuation_text(cells: list[str]) -> str:
    non_empty_cells = [clean_cell_value(cell) for cell in cells if clean_cell_value(cell)]
    return " | ".join(non_empty_cells)


def collapse_continuation_rows(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty and len(dataframe.columns) == 0:
        return dataframe

    dataframe = ensure_minimum_columns(dataframe, minimum_columns=5)
    rows = [
        [clean_cell_value(value) for value in row.tolist()]
        for _, row in dataframe.iterrows()
    ]

    collapsed_rows = []
    previous_number = None

    for row_index, row in enumerate(rows):
        if not any(normalize_compare_text(value) for value in row):
            continue

        if is_header_row_values(row):
            continue

        current_number = extract_leading_number(row[0]) if row else None

        if row_index == 0 or not collapsed_rows:
            collapsed_rows.append(row)
            previous_number = current_number
            continue

        should_start_new_row = False
        if current_number is not None:
            if current_number == 1:
                should_start_new_row = True
            elif previous_number is None:
                should_start_new_row = True
            elif current_number >= previous_number:
                should_start_new_row = True

        if should_start_new_row:
            collapsed_rows.append(row)
            previous_number = current_number
            continue

        continuation_text = row_to_continuation_text(row)
        collapsed_rows[-1][4] = append_with_blank_line(
            collapsed_rows[-1][4],
            continuation_text,
        )

    if not collapsed_rows:
        return pd.DataFrame(columns=dataframe.columns)

    return pd.DataFrame(collapsed_rows, columns=dataframe.columns)


def normalize_section_block(dataframe: pd.DataFrame) -> pd.DataFrame:
    dataframe = clean_table_dataframe(dataframe)
    if dataframe.empty and len(dataframe.columns) == 0:
        return dataframe

    dataframe = promote_first_row_to_header_if_needed(dataframe)
    dataframe = clean_table_dataframe(dataframe)
    dataframe = collapse_continuation_rows(dataframe)
    dataframe = clean_table_dataframe(dataframe)
    return dataframe


def split_dataframe_by_section_markers(
    dataframe: pd.DataFrame,
    fallback_section: str | None,
) -> tuple[list[dict], str | None]:
    if dataframe.empty and len(dataframe.columns) == 0:
        return [], fallback_section

    blocks = []
    current_section = fallback_section
    last_section = fallback_section
    current_rows = []
    columns = list(dataframe.columns)

    for _, row in dataframe.iterrows():
        row_values = [clean_cell_value(value) for value in row.tolist()]
        row_text = row_cells_to_text(row_values)
        if not row_text:
            continue

        detected_section = detect_section_from_text(row_text)
        if detected_section is not None:
            if current_rows and current_section in TARGET_SECTIONS:
                blocks.append(
                    {
                        "section_name": current_section,
                        "dataframe": pd.DataFrame(current_rows, columns=columns),
                    }
                )
            current_section = detected_section
            last_section = detected_section
            current_rows = []
            continue

        if current_section in TARGET_SECTIONS:
            current_rows.append(row_values)

    if current_rows and current_section in TARGET_SECTIONS:
        blocks.append(
            {
                "section_name": current_section,
                "dataframe": pd.DataFrame(current_rows, columns=columns),
            }
        )

    return blocks, last_section


def drop_header_like_rows(dataframe: pd.DataFrame, reference_columns: list[str]) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe

    normalized_columns = [normalize_compare_text(column) for column in reference_columns]

    def is_header_like(row: pd.Series) -> bool:
        normalized_row = [normalize_compare_text(value) for value in row.tolist()]
        return normalized_row == normalized_columns

    mask = ~dataframe.apply(is_header_like, axis=1)
    return dataframe.loc[mask].reset_index(drop=True)


def merge_table_blocks(blocks: list[dict]) -> pd.DataFrame:
    merged_dataframe = pd.DataFrame()
    reference_columns = []

    for block in blocks:
        dataframe = clean_table_dataframe(block["dataframe"])
        if dataframe.empty and len(dataframe.columns) == 0:
            continue

        if merged_dataframe.empty and not reference_columns:
            merged_dataframe = dataframe.reset_index(drop=True)
            reference_columns = list(merged_dataframe.columns)
            continue

        if len(dataframe.columns) == len(reference_columns):
            dataframe.columns = reference_columns
        else:
            all_columns = reference_columns.copy()
            for column in dataframe.columns:
                if column not in all_columns:
                    all_columns.append(column)

            merged_dataframe = merged_dataframe.reindex(columns=all_columns)
            dataframe = dataframe.reindex(columns=all_columns)
            reference_columns = all_columns

        dataframe = drop_header_like_rows(dataframe, reference_columns)
        merged_dataframe = pd.concat(
            [merged_dataframe, dataframe],
            ignore_index=True,
        )

    return merged_dataframe


#------------------------------
# 선택 표 추출
#------------------------------
def format_page_numbers(pages: set[int]) -> str:
    if not pages:
        return "-"

    sorted_pages = sorted(pages)
    ranges = []
    range_start = sorted_pages[0]
    range_end = sorted_pages[0]

    for page in sorted_pages[1:]:
        if page == range_end + 1:
            range_end = page
        else:
            ranges.append(
                f"{range_start}" if range_start == range_end else f"{range_start}-{range_end}"
            )
            range_start = page
            range_end = page

    ranges.append(
        f"{range_start}" if range_start == range_end else f"{range_start}-{range_end}"
    )
    return ", ".join(ranges)


def extract_selected_section_tables(result: dict) -> dict:
    section_tables = {
        section_name: {
            "display_name": SECTION_LABELS[section_name],
            "blocks": [],
            "pages": set(),
            "dataframe": pd.DataFrame(),
            "row_count": 0,
            "block_count": 0,
            "page_text": "-",
        }
        for section_name in TARGET_SECTIONS
    }

    current_section = None
    elements = sorted(
        result.get("elements", []),
        key=lambda element: (
            element.get("page") or 0,
            element.get("id") or 0,
        ),
    )

    for element in elements:
        if not is_table_element(element):
            search_text = get_element_search_text(element)
            detected_section = detect_section_from_text(search_text)
            if detected_section is not None:
                current_section = detected_section
            continue

        dataframes = extract_table_dataframes(element)
        if not dataframes:
            continue

        for dataframe in dataframes:
            split_blocks, current_section = split_dataframe_by_section_markers(
                dataframe,
                current_section,
            )

            for block in split_blocks:
                section_name = block["section_name"]
                normalized_dataframe = normalize_section_block(block["dataframe"])
                if normalized_dataframe.empty and len(normalized_dataframe.columns) == 0:
                    continue

                section_tables[section_name]["blocks"].append(
                    {
                        "page": element.get("page"),
                        "dataframe": normalized_dataframe,
                    }
                )

                if element.get("page") is not None:
                    section_tables[section_name]["pages"].add(element.get("page"))

    for section_name, section_info in section_tables.items():
        merged_dataframe = merge_table_blocks(section_info["blocks"])
        section_info["dataframe"] = merged_dataframe
        section_info["row_count"] = len(merged_dataframe.index)
        section_info["block_count"] = len(section_info["blocks"])
        section_info["page_text"] = format_page_numbers(section_info["pages"])

    return section_tables


#------------------------------
# 엑셀 변환
#------------------------------
def make_section_excel_bytes(
    file_name: str,
    section_name: str,
    section_info: dict,
) -> bytes:
    output = io.BytesIO()
    dataframe = section_info["dataframe"]
    summary_df = pd.DataFrame(
        [
            {
                "file_name": file_name,
                "section": section_info["display_name"],
                "pages": section_info["page_text"],
                "row_count": section_info["row_count"],
                "block_count": section_info["block_count"],
            }
        ]
    )

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="summary", index=False)
        dataframe.to_excel(writer, sheet_name=section_name, index=False)

    return output.getvalue()


def make_combined_excel_bytes(file_name: str, section_tables: dict) -> bytes:
    output = io.BytesIO()
    summary_rows = []

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for section_name in TARGET_SECTIONS:
            section_info = section_tables[section_name]
            summary_rows.append(
                {
                    "file_name": file_name,
                    "section": section_info["display_name"],
                    "pages": section_info["page_text"],
                    "row_count": section_info["row_count"],
                    "block_count": section_info["block_count"],
                }
            )

            dataframe = section_info["dataframe"]
            if not dataframe.empty or len(dataframe.columns) > 0:
                dataframe.to_excel(writer, sheet_name=section_name, index=False)

        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="summary", index=False)

    return output.getvalue()


#------------------------------
# 결과 요약
#------------------------------
def get_page_count(result: dict) -> int:
    pages = {
        element.get("page")
        for element in result.get("elements", [])
        if element.get("page") is not None
    }
    return len(pages)


def get_file_signature(file_bytes: bytes) -> str:
    return hashlib.sha1(file_bytes).hexdigest()


require_password()

#------------------------------
# 메인 화면
#------------------------------
st.title("DOVI (Upstage version)")
st.success("비밀번호 확인 완료")

#------------------------------
# Upstage API Key 입력
#------------------------------
default_api_key = os.getenv("UPSTAGE_API_KEY", "")
upstage_api_key = st.text_input(
    "Upstage API Key",
    value=default_api_key,
    type="password",
    help="환경변수 UPSTAGE_API_KEY가 있으면 자동으로 채워집니다.",
)

#------------------------------
# PDF 파일 업로드
#------------------------------
st.write("pdf 파일을 업로드 해주세요.")

uploaded_pdf = st.file_uploader(
    "PDF 파일을 업로드 해주세요.",
    type=["pdf"],
    accept_multiple_files=False,
)

if uploaded_pdf is not None:
    pdf_bytes = uploaded_pdf.getvalue()
    file_size_kb = uploaded_pdf.size / 1024
    file_signature = get_file_signature(pdf_bytes)

    st.info(f"업로드된 파일: {uploaded_pdf.name}")
    st.caption(f"파일 크기: {file_size_kb:.1f} KB")

    if st.button("Upstage OCR 실행", type="primary"):
        if not upstage_api_key.strip():
            st.error("Upstage API Key를 먼저 입력해주세요.")
        else:
            try:
                with st.spinner("Upstage OCR 결과에서 표제부, 갑구, 을구 표를 재구성하고 있습니다..."):
                    result = call_upstage_document_parse(
                        file_name=uploaded_pdf.name,
                        file_bytes=pdf_bytes,
                        api_key=upstage_api_key.strip(),
                    )
                    section_tables = extract_selected_section_tables(result)
                    combined_excel_bytes = make_combined_excel_bytes(
                        uploaded_pdf.name,
                        section_tables,
                    )

                    st.session_state["ocr_result"] = result
                    st.session_state["section_tables"] = section_tables
                    st.session_state["combined_excel_bytes"] = combined_excel_bytes
                    st.session_state["ocr_file_signature"] = file_signature
            except Exception as exc:
                st.error(str(exc))

    if st.session_state.get("ocr_file_signature") == file_signature:
        result = st.session_state.get("ocr_result", {})
        section_tables = st.session_state.get("section_tables", {})
        combined_excel_bytes = st.session_state.get("combined_excel_bytes", b"")

        page_count = get_page_count(result)
        found_section_count = sum(
            1
            for section_name in TARGET_SECTIONS
            if section_name in section_tables
            and (
                not section_tables[section_name]["dataframe"].empty
                or len(section_tables[section_name]["dataframe"].columns) > 0
            )
        )
        total_row_count = sum(
            section_tables[section_name]["row_count"]
            for section_name in TARGET_SECTIONS
            if section_name in section_tables
        )

        col1, col2, col3 = st.columns(3)
        col1.metric("파일명", uploaded_pdf.name)
        col2.metric("페이지 수", page_count)
        col3.metric("추출된 표 수", found_section_count)
        st.caption(f"재구성된 전체 행 수: {total_row_count}")

        st.download_button(
            label="선택 표 전체 엑셀 다운로드",
            data=combined_excel_bytes,
            file_name=f"{uploaded_pdf.name.rsplit('.', 1)[0]}_selected_tables.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            key=f"download_all_{file_signature}",
        )

        if found_section_count == 0:
            st.warning("표제부, 갑구, 을구 표를 찾지 못했습니다.")

        section_tabs = st.tabs([SECTION_LABELS[name] for name in TARGET_SECTIONS])

        for tab, section_name in zip(section_tabs, TARGET_SECTIONS):
            section_info = section_tables.get(section_name)
            dataframe = section_info["dataframe"] if section_info else pd.DataFrame()

            with tab:
                if section_info is None or (
                    dataframe.empty and len(dataframe.columns) == 0
                ):
                    st.warning(f"{SECTION_LABELS[section_name]} 표를 찾지 못했습니다.")
                    continue

                st.caption(
                    f"페이지: {section_info['page_text']} | "
                    f"표 블록 수: {section_info['block_count']} | "
                    f"행 수: {section_info['row_count']}"
                )

                section_excel_bytes = make_section_excel_bytes(
                    uploaded_pdf.name,
                    section_name,
                    section_info,
                )

                st.download_button(
                    label=f"{SECTION_LABELS[section_name]} 엑셀 다운로드",
                    data=section_excel_bytes,
                    file_name=(
                        f"{uploaded_pdf.name.rsplit('.', 1)[0]}_{section_name}.xlsx"
                    ),
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    key=f"download_{section_name}_{file_signature}",
                )

                st.dataframe(dataframe, use_container_width=True)

        with st.expander("OCR 원본 응답 보기"):
            st.json(result)
