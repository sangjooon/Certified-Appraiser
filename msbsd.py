#이 코드는 개발용 코드임

import streamlit as st
import pandas as pd






#main 함수
def main():
    
    #페이지 상단 및 설정
    st.set_page_config(
        page_title="문서 비서",
        page_icon="📄", #이모지 유니코드: U+1F4C4
        layout="wide"
    )
    
    #제목
    st.title("문서 비서📄")
    #서비스 설명
    st.markdown(
        """
        문서 비서는 다양한 형식의 문서를 텍스트로 변환하고, 
        사용자가 원하는 핵심 데이터를 추출하는 도구입니다.
        """
    )
    
    #비밀번호(임시)
    password = st.text_input("비밀번호를 입력하세요:", type="password")
    if password != "alohomora":
        st.warning("비밀번호가 올바르지 않습니다.")
        return
    
    
    




#실행
if __name__ == "__main__":
    main()

