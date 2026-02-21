# OCR app entrypoint
import hashlib

import pandas as pd
import streamlit as st

from app_core.pipeline import process_pdf

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
    st.subheader("토지의 소재지를 출력하는 프로토타입 v0.0.5")
    st.subheader("v0.0.4에서 코드 정리 및 주석 보강")

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
