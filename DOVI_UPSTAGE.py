# DOVI (Upstage version)
# version 0.0.0

import hmac

import pandas as pd
import streamlit as st

# ---------------------------------
# 비밀번호 alohomora
# ---------------------------------

APP_PASSWORD = "alohomora"


def require_password() -> None:
    if st.session_state.get("password_ok", False):
        return

    st.title("DOVI (Upstage version)")
    st.write("Enter the password to continue.")

    with st.form("password_form", clear_on_submit=True):
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Continue")

    if submitted:
        if hmac.compare_digest(password, APP_PASSWORD):
            st.session_state["password_ok"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")

    st.stop()


require_password()

st.title("DOVI (Upstage version)")
st.success("Password verified.")
