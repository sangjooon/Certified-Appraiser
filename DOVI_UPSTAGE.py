# DOVI (Upstage version)
# version 0.0.0

import hashlib
import hmac
import io
import json
import os

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
# Markdown 추출
#------------------------------
def extract_markdown_content(result: dict) -> str:
    content = result.get("content", {})
    markdown_text = content.get("markdown", "")
    if markdown_text.strip():
        return markdown_text

    markdown_parts = []
    for element in result.get("elements", []):
        element_content = element.get("content", {})
        element_markdown = element_content.get("markdown", "")
        if element_markdown.strip():
            markdown_parts.append(element_markdown.strip())

    if markdown_parts:
        return "\n\n".join(markdown_parts)

    text_content = content.get("text", "")
    if text_content.strip():
        return text_content

    html_content = content.get("html", "")
    if html_content.strip():
        return html_content

    return ""


#------------------------------
# 엑셀 변환
#------------------------------
def make_excel_bytes(file_name: str, markdown_text: str, result: dict) -> bytes:
    markdown_lines = markdown_text.splitlines() or [markdown_text]
    full_markdown_df = pd.DataFrame(
        [
            {
                "file_name": file_name,
                "markdown": markdown_text,
            }
        ]
    )
    markdown_lines_df = pd.DataFrame(
        {
            "line_no": range(1, len(markdown_lines) + 1),
            "markdown_line": markdown_lines,
        }
    )

    element_rows = []
    for element in result.get("elements", []):
        element_content = element.get("content", {})
        element_rows.append(
            {
                "id": element.get("id"),
                "page": element.get("page"),
                "category": element.get("category"),
                "markdown": element_content.get("markdown", ""),
                "text": element_content.get("text", ""),
                "html": element_content.get("html", ""),
            }
        )

    elements_df = pd.DataFrame(element_rows)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        full_markdown_df.to_excel(writer, sheet_name="markdown_full", index=False)
        markdown_lines_df.to_excel(writer, sheet_name="markdown_lines", index=False)

        if not elements_df.empty:
            elements_df.to_excel(writer, sheet_name="elements", index=False)

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
                with st.spinner("Upstage OCR로 PDF를 Markdown으로 변환하고 있습니다..."):
                    result = call_upstage_document_parse(
                        file_name=uploaded_pdf.name,
                        file_bytes=pdf_bytes,
                        api_key=upstage_api_key.strip(),
                    )
                    markdown_text = extract_markdown_content(result)

                    st.session_state["uploaded_pdf_name"] = uploaded_pdf.name
                    st.session_state["ocr_result"] = result
                    st.session_state["ocr_markdown"] = markdown_text
                    st.session_state["ocr_excel_bytes"] = make_excel_bytes(
                        uploaded_pdf.name,
                        markdown_text,
                        result,
                    )
                    st.session_state["ocr_file_signature"] = file_signature
            except Exception as exc:
                st.error(str(exc))

    if st.session_state.get("ocr_file_signature") == file_signature:
        result = st.session_state.get("ocr_result", {})
        markdown_text = st.session_state.get("ocr_markdown", "")
        excel_bytes = st.session_state.get("ocr_excel_bytes", b"")
        page_count = get_page_count(result)
        element_count = len(result.get("elements", []))

        col1, col2, col3 = st.columns(3)
        col1.metric("파일명", uploaded_pdf.name)
        col2.metric("페이지 수", page_count)
        col3.metric("인식 요소 수", element_count)

        st.download_button(
            label="Markdown 엑셀 다운로드",
            data=excel_bytes,
            file_name=f"{uploaded_pdf.name.rsplit('.', 1)[0]}_upstage_markdown.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )

        st.download_button(
            label="Markdown 원문 다운로드",
            data=markdown_text.encode("utf-8"),
            file_name=f"{uploaded_pdf.name.rsplit('.', 1)[0]}_upstage_markdown.md",
            mime="text/markdown",
        )

        preview_tab, raw_tab, json_tab = st.tabs(
            ["미리보기", "원문 Markdown", "응답 JSON"]
        )

        with preview_tab:
            st.markdown(markdown_text)

        with raw_tab:
            st.code(markdown_text, language="markdown")

        with json_tab:
            st.json(result)
