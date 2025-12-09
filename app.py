import streamlit as st
import ffmpeg
import os
import math
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime

# 設定頁面資訊
st.set_page_config(page_title="音檔切割小幫手 (FFmpeg版)", page_icon="✂️")
st.title("✂️ 智慧音檔切割與寄送系統")
st.caption("🚀 核心已升級為 FFmpeg 引擎，不受 Python 版本限制。")

# --- 核心邏輯函式區 (FFmpeg Direct) ---

def get_audio_info(file_path):
    """使用 ffprobe 獲取音訊資訊 (時長與大小)"""
    try:
        probe = ffmpeg.probe(file_path)
        duration = float(probe['format']['duration'])
        size = float(probe['format']['size'])
        return duration, size
    except ffmpeg.Error as e:
        st.error(f"讀取音訊資訊失敗: {e.stderr}")
        return None, None

def split_audio_ffmpeg(input_path, target_size_mb=9.5):
    """
    使用 FFmpeg 的 segment 功能進行切割
    邏輯：計算 bitrate -> 推算 9.5MB 對應的秒數 -> 執行切割
    """
    duration, size_bytes = get_audio_info(input_path)
    if not duration:
        return []

    target_bytes = target_size_mb * 1024 * 1024
    
    # 如果檔案本來就比較小，直接回傳原檔
    if size_bytes <= target_bytes:
        return [input_path]

    # 計算平均位元率 (Bytes per second)
    avg_bitrate = size_bytes / duration
    
    # 計算每個片段的目標時長 (秒) = 目標大小 / 位元率
    # 乘上 0.95 做安全係數，避免邊緣誤差導致超過 10MB
    segment_time = (target_bytes / avg_bitrate) * 0.95
    
    # 建立輸出檔名格式
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_pattern = f"rec_{timestamp}_part%03d.mp3"
    
    try:
        # 執行 FFmpeg 切割指令
        # -c copy 表示「直接複製串流」，不重新編碼 (速度快、不損音質)
        # -f segment 指定使用分段器
        (
            ffmpeg
            .input(input_path)
            .output(output_pattern, c='copy', f='segment', segment_time=segment_time, reset_timestamps=1)
            .run(quiet=True, overwrite_output=True)
        )
        
        # 找出生成的所有檔案
        generated_files = []
        for file in sorted(os.listdir('.')):
            if file.startswith(f"rec_{timestamp}") and file.endswith(".mp3"):
                generated_files.append(file)
                
        return generated_files
        
    except ffmpeg.Error as e:
        st.error(f"切割失敗: {e.stderr.decode('utf8')}")
        return []

def send_email(to_email, selected_files, sender_email, sender_password):
    """發送 Email (維持不變)"""
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = to_email
    msg['Subject'] = "您的音訊檔案片段"
    msg.attach(MIMEText("您好，這是您選擇的音訊切割檔案 (由 FFmpeg 引擎處理)。", 'plain'))

    for filename in selected_files:
        # 從硬碟讀取檔案
        with open(filename, "rb") as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f"attachment; filename= {filename}")
            msg.attach(part)

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, msg.as_string())
        server.quit()
        return True, "發送成功！"
    except Exception as e:
        return False, str(e)

# --- 使用者介面區 ---

uploaded_file = st.file_uploader("第一步：上傳錄音檔", type=['mp3', 'wav', 'm4a'])

if 'generated_files' not in st.session_state:
    st.session_state['generated_files'] = []

if uploaded_file is not None:
    # 為了讓 FFmpeg 讀取，必須先將上傳的檔案存到暫存區
    temp_filename = "temp_input_audio" + os.path.splitext(uploaded_file.name)[1]
    
    # 只有當 session 是空的時候才執行切割
    if not st.session_state['generated_files']:
        with open(temp_filename, "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        with st.spinner('🚀 正在使用 FFmpeg 引擎進行極速切割...'):
            files = split_audio_ffmpeg(temp_filename)
            if files:
                st.session_state['generated_files'] = files
                st.success(f"切割完成！產生 {len(files)} 個檔案。")
            
            # 清理暫存原始檔
            if os.path.exists(temp_filename):
                os.remove(temp_filename)

    # 顯示檔案列表
    if st.session_state['generated_files']:
        st.subheader("第二步：選擇要寄送的片段")
        
        selected_files = []
        for f_name in st.session_state['generated_files']:
            file_size = os.path.getsize(f_name) / (1024 * 1024)
            if st.checkbox(f"{f_name} ({file_size:.2f} MB)", value=True):
                selected_files.append(f_name)
        
        st.subheader("第三步：輸入收件資訊")
        recipient_email = st.text_input("收件者信箱")
        
        if st.button("寄送檔案"):
            if not recipient_email:
                st.warning("請輸入 Email")
            elif not selected_files:
                st.warning("請選擇檔案")
            else:
                try:
                    sender_email = st.secrets["email"]["username"]
                    sender_password = st.secrets["email"]["password"]
                    with st.spinner("寄信中..."):
                        success, msg = send_email(recipient_email, selected_files, sender_email, sender_password)
                        if success:
                            st.balloons()
                            st.success(msg)
                        else:
                            st.error(msg)
                except Exception as e:
                    st.error(f"Secrets 設定錯誤或遺失: {e}")

# 清理舊檔案機制 (可選)
# 實際部署時，Streamlit Cloud 會定期重置，或可在這裡加入清理邏輯
