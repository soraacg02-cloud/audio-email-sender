import streamlit as st
from pydub import AudioSegment
import io
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
import os
from datetime import datetime

# 設定頁面資訊
st.set_page_config(page_title="音檔切割小幫手", page_icon="✂️")

st.title("✂️ 智慧音檔切割與寄送系統")

# --- 新增：提示訊息，防止瀏覽器翻譯導致錯誤 ---
st.caption("💡 提示：若介面出現 'removeChild' 錯誤，請務必 **關閉瀏覽器的自動翻譯功能** 並重新整理網頁。")
st.markdown("---")

# --- 邏輯函式區 ---

def split_audio(audio_file):
    """將音訊切割成小於目標大小的片段 (預設接近 10MB)"""
    # 讀取音訊
    audio = AudioSegment.from_file(audio_file)
    
    # 計算檔案大小與長度
    # 設定目標為 9.5MB 以確保不超過 10MB 限制
    limit_bytes = 9.5 * 1024 * 1024
    
    # 取得音訊的位元率 (byte per millisecond)
    byte_rate = audio.frame_rate * audio.sample_width * audio.channels / 1000
    
    # 計算每個片段的最大毫秒數
    chunk_length_ms = int(limit_bytes / byte_rate)
    
    chunks = []
    # 切割迴圈
    for i in range(0, len(audio), chunk_length_ms):
        chunk = audio[i : i + chunk_length_ms]
        chunks.append(chunk)
        
    return chunks

def send_email(to_email, selected_files, sender_email, sender_password):
    """發送帶有附件的 Email"""
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = to_email
    msg['Subject'] = "您的音訊檔案片段"
    
    body = "您好，這是您選擇的音訊切割檔案，請查收。"
    msg.attach(MIMEText(body, 'plain'))

    for filename, file_bytes in selected_files:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(file_bytes)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename= {filename}")
        msg.attach(part)

    try:
        # 使用 Gmail SMTP
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        text = msg.as_string()
        server.sendmail(sender_email, to_email, text)
        server.quit()
        return True, "發送成功！"
    except Exception as e:
        return False, str(e)

# --- 使用者介面區 ---

uploaded_file = st.file_uploader("第一步：上傳錄音檔 (支援 mp3, wav, m4a)", type=['mp3', 'wav', 'm4a'])

# 初始化 session state
if 'chunks_data' not in st.session_state:
    st.session_state['chunks_data'] = []

if uploaded_file is not None:
    # 若 session 為空則執行切割
    if not st.session_state['chunks_data']:
        with st.spinner('正在分析並切割音檔，請稍候...'):
            try:
                chunks = split_audio(uploaded_file)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M")
                
                for idx, chunk in enumerate(chunks):
                    # 將 chunk 轉回 bytes
                    buf = io.BytesIO()
                    chunk.export(buf, format="mp3")
                    file_name = f"rec_{timestamp}_part{idx+1}.mp3"
                    st.session_state['chunks_data'].append((file_name, buf.getvalue()))
                
                st.success(f"切割完成！共產生 {len(chunks)} 個檔案。")
            except Exception as e:
                st.error(f"處理檔案時發生錯誤：{e}")

    # 第二步：顯示與選擇
    if st.session_state['chunks_data']:
        st.subheader("第二步：選擇要寄送的片段")
        
        selected_options = []
        # 使用 enumerate 確保 key 唯一，防止介面錯誤
        for idx, (name, data) in enumerate(st.session_state['chunks_data']):
            if st.checkbox(f"{name} ({len(data)/1024/1024:.2f} MB)", value=True, key=f"chk_{idx}"):
                selected_options.append((name, data))
        
        st.subheader("第三步：輸入收件資訊")
        recipient_email = st.text_input("收件者信箱")
        
        if st.button("寄送檔案"):
            if not recipient_email:
                st.warning("請輸入 Email 地址")
            elif not selected_options:
                st.warning("請至少選擇一個檔案")
            else:
                # 從 Secrets 讀取帳密
                try:
                    sender_email = st.secrets["email"]["username"]
                    sender_password = st.secrets["email"]["password"]
                    
                    with st.spinner("正在寄信中..."):
                        success, msg = send_email(recipient_email, selected_options, sender_email, sender_password)
                        if success:
                            st.balloons()
                            st.success(msg)
                        else:
                            st.error(f"寄送失敗：{msg}")
                except FileNotFoundError:
                     st.error("找不到 Secrets 設定。請在 Streamlit Cloud 設定 Email 帳密。")
                except KeyError:
                     st.error("Secrets 格式錯誤。請確認包含 [email] 區塊以及 username 和 password。")
