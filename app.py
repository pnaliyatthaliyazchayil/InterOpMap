import streamlit as st

st.set_page_config(page_title="Test", layout="wide")

st.title("🧬 Debug Test")

tab1, tab2 = st.tabs(["Tab 1", "Tab 2"])

with tab1:
    st.write("✅ Tab 1 works")
    
with tab2:
    st.write("✅ Tab 2 works!")
    
    st.markdown("""
    <div style="background: #ecfdf5; padding: 1rem; border-radius: 8px;">
        If you can see this green box, tab2 is rendering!
    </div>
    """, unsafe_allow_html=True)
    
    st.text_input("API Key", type="password", key="test_api")
    st.text_input("Name", key="test_name")
    st.button("Test Button")
    
    col1, col2 = st.columns([3, 2])
    with col1:
        st.write("Left column")
    with col2:
        st.write("Right column")

st.success("✅ File executed successfully - both tabs should be visible")
