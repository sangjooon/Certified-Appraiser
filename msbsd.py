#이 코드는 개발용 코드임

import streamlit as st
import pandas as pd






#main 함수
def main():
    
    #페이지 상단 및 설정
    st.set_page_config(
        page_title="문서 비서",
        page_icon="📄",
        layout="wide"
    )
    
    #제목
    st.title("문서 비서📄")
    st.markdown(
        """
        문서 비서는 다양한 형식의 문서를 텍스트로 변환하고, 
        사용자가 원하는 핵심 데이터를 추출하는 도구입니다.
        """
    )
    
    




#실행
if __name__ == "__main__":
    main()

