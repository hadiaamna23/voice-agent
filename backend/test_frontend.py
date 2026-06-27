import streamlit as st
import requests

BACKEND_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="Backend Tester")

st.title("🚀 AI Voice Agent Backend Test")

# =====================================================
# REGISTER
# =====================================================

st.header("1. Register")

email = st.text_input("Email")
password = st.text_input("Password", type="password")

if st.button("Register"):

    payload = {
        "email": email,
        "password": password,
        "tenant_id": "test"
    }

    try:
        r = requests.post(
            f"{BACKEND_URL}/api/auth/register",
            json=payload,
            timeout=20
        )

        st.write(r.status_code)
        st.json(r.json())

    except Exception as e:
        st.error(str(e))

# =====================================================
# LOGIN
# =====================================================

st.header("2. Login")

if st.button("Login"):

    payload = {
        "username": email,
        "password": password
    }

    try:

        r = requests.post(
            f"{BACKEND_URL}/api/auth/token",
            data=payload,
            timeout=20
        )

        st.write(r.status_code)

        data = r.json()

        st.json(data)

        if "access_token" in data:
            st.session_state.token = data["access_token"]
            st.success("JWT Token Generated")

    except Exception as e:
        st.error(str(e))

# =====================================================
# SYNTHESIZE
# =====================================================

st.header("3. Voice Synthesize")

text = st.text_area(
    "Text",
    "Hello this is backend testing"
)

if st.button("Test Voice"):

    token = st.session_state.get("token")

    if not token:
        st.error("Login first")
        st.stop()

    headers = {
        "Authorization": f"Bearer {token}"
    }

    payload = {
        "text": text,
        "voice_id": "test",
        "language": "en"
    }

    try:

        r = requests.post(
            f"{BACKEND_URL}/api/voice/synthesize",
            json=payload,
            headers=headers,
            timeout=60
        )

        st.write(r.status_code)
        st.json(r.json())

        if r.status_code == 200:
            st.success("Voice endpoint working")

    except Exception as e:
        st.error(str(e))