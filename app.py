import streamlit as st
import os
from pydub import AudioSegment
import math
import io
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime

# --- 設定頁面：標題與佈局 ---
st.set_page_config(page_title="音訊切割助手", page_icon="📱", layout="centered")

# --- CSS 優化 (針對手機微調) ---
st.markdown("""
    <style>
    .stButton>button {
        height: 3em;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 初始化 Session State ---
if 'is_logged_in' not in st.session_state:
    st.session_state['is_logged_in'] = False
if 'user_credentials' not in st.session_state:
    st.session_state['user_credentials'] = {}
if 'processed_files' not in st.session_state:
    st.session_state['processed_files'] = []

# --- 核心邏輯函數 ---
def try_login(email, password):
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(email, password)
        server.quit()
        return True, "驗證成功"
    except Exception as e:
        return False, f"登入失敗: {str(e)}"

def split_audio(uploaded_file, target_size_mb=9.5):
    """
    切割並重新命名：[案號] [空格] [001]
    """
    audio = AudioSegment.from_file(uploaded_file)
    file_size = uploaded_file.size
    duration_ms = len(audio)
    target_size_bytes = target_size_mb * 1024 * 1024
    
    chunks = []
    # 取得原始檔名 (不含副檔名)，作為案號
    base_name = os.path.splitext(uploaded_file.name)[0]
    export_format = "mp3" 

    if file_size <= target_size_bytes:
        # 即使不切割，也統一加上 001
        buffer = io.BytesIO()
        audio.export(buffer, format=export_format)
        chunks.append({
            "name": f"{base_name} 001.{export_format}", 
            "data": buffer.getvalue()
        })
    else:
        num_parts = math.ceil(file_size / target_size_bytes)
        chunk_length_ms = math.ceil(duration_ms / num_parts)
        
        st.toast(f"檔案較大，正在切割成 {num_parts} 份...", icon="🔪")

        for i in range(num_parts):
            start_time = i * chunk_length_ms
            end_time = min((i + 1) * chunk_length_ms, duration_ms)
            chunk = audio[start_time:end_time]
            buffer = io.BytesIO()
            chunk.export(buffer, format=export_format)
            
            # 命名規則：原檔名 + 空格 + 三位數編碼
            timestamp_idx = i + 1
            file_name = f"{base_name} {timestamp_idx:03d}.{export_format}"
            
            chunks.append({
                "name": file_name,
                "data": buffer.getvalue()
            })
    return chunks

def send_email(sender_email, sender_password, receiver_email, subject, body, files_to_send):
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    for file_info in files_to_send:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(file_info['data'])
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename= {file_info["name"]}')
        msg.attach(part)

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        text = msg.as_string()
        server.sendmail(sender_email, receiver_email, text)
        server.quit()
        return True, "成功寄出！"
    except Exception as e:
        return False, f"失敗: {str(e)}"

# ================= 介面流程 =================

st.title("📱 音訊切割寄信助手")

# --- Step 1: 登入 ---
if not st.session_state['is_logged_in']:
    st.warning("請先連結 Gmail")
    
    with st.container(border=True):
        email_input = st.text_input("Gmail 帳號", placeholder="example@gmail.com")
        pwd_input = st.text_input("應用程式密碼", type="password")
        st.caption("⚠️ 請至 Google 帳戶 > 安全性 > 申請「應用程式密碼」(非登入密碼)")
        
        if st.button("🔗 連結並登入", type="primary", use_container_width=True):
            if not email_input or not pwd_input:
                st.error("請輸入完整資訊")
            else:
                with st.spinner("連線中..."):
                    success, msg = try_login(email_input, pwd_input)
                    if success:
                        st.session_state['is_logged_in'] = True
                        st.session_state['user_credentials'] = {'email': email_input, 'pwd': pwd_input}
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

else:
    # --- 已登入狀態 ---
    with st.expander(f"👤 已登入: {st.session_state['user_credentials']['email']}", expanded=False):
        if st.button("登出切換帳號", use_container_width=True):
            st.session_state['is_logged_in'] = False
            st.session_state['user_credentials'] = {}
            st.session_state['processed_files'] = []
            st.rerun()

    st.markdown("---")

    # --- Step 2: 上傳 ---
    st.subheader("1. 上傳錄音檔")
    uploaded_file = st.file_uploader("點擊上傳 (支援 mp3, wav, m4a...)", type=['mp3', 'wav', 'm4a', 'ogg'], label_visibility="collapsed")
    
    if uploaded_file:
        st.caption(f"檔案: {uploaded_file.name} | 大小: {uploaded_file.size/(1024*1024):.1f} MB")
        
        if st.button("✂️ 開始處理 / 切割", type="primary", use_container_width=True):
            with st.spinner("正在處理音訊..."):
                try:
                    chunks = split_audio(uploaded_file)
                    st.session_state['processed_files'] = chunks
                    st.toast(f"處理完成！共 {len(chunks)} 個檔案", icon="✅")
                except Exception as e:
                    st.error(f"錯誤: {e}")

    # --- Step 3: 寄送 ---
    if st.session_state['processed_files']:
        st.markdown("---")
        st.subheader("2. 寄送檔案")
        
        with st.container(border=True):
            # 檔案選擇
            all_filenames = [f['name'] for f in st.session_state['processed_files']]
            selected_files = st.multiselect("選擇附件", options=all_filenames, default=all_filenames)
            st.caption(f"已選 {len(selected_files)} 個檔案")
            
            # 收件資訊
            receiver_email = st.text_input("收件者 Email", placeholder="receiver@example.com")
            email_subject = st.text_input("信件主旨", value=f"錄音檔 ({datetime.now().strftime('%m/%d')})")
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            if st.button("🚀 確認發送郵件", type="primary", use_container_width=True):
                if not receiver_email:
                    st.toast("請填寫收件人！", icon="⚠️")
                elif not selected_files:
                    st.toast("請至少選一個檔案！", icon="⚠️")
                else:
                    files_payload = [f for f in st.session_state['processed_files'] if f['name'] in selected_files]
                    
                    with st.spinner("郵件發送中..."):
                        success, msg = send_email(
                            st.session_state['user_credentials']['email'],
                            st.session_state['user_credentials']['pwd'],
                            receiver_email,
                            email_subject,
                            "附件為切割後的音檔，請查收。",
                            files_payload
                        )
                        if success:
                            st.success("✅ 寄送成功！")
                            st.balloons()
                        else:
                            st.error(msg)
