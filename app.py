import streamlit as st
import ffmpeg
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime

# 設定頁面資訊
st.set_page_config(page_title="音檔切割小幫手 (FFmpeg V2)", page_icon="✂️")
st.title("✂️ 智慧音檔切割與寄送系統")
st.caption("🚀 核心 V2：已支援 M4A/WAV/MP3 原格式無損切割。")
st.caption("💡 若按鈕無反應，請務必 **關閉瀏覽器的自動翻譯**。")

# --- 核心邏輯函式區 ---

def get_audio_info(file_path):
    """使用 ffprobe 獲取音訊資訊"""
    try:
        probe = ffmpeg.probe(file_path)
        duration = float(probe['format']['duration'])
        size = float(probe['format']['size'])
        return duration, size
    except ffmpeg.Error as e:
        return None, None

def split_audio_ffmpeg(input_path, target_size_mb=9.5):
    """
    自動辨識副檔名並進行切割
    """
    duration, size_bytes = get_audio_info(input_path)
    if not duration:
        st.error("無法讀取音訊資訊，請確認檔案是否損壞。")
        return []

    target_bytes = target_size_mb * 1024 * 1024
    
    # 若檔案小於目標，直接回傳原檔
    if size_bytes <= target_bytes:
        return [input_path]

    # 計算切割時間點
    avg_bitrate = size_bytes / duration
    segment_time = (target_bytes / avg_bitrate) * 0.95
    
    # --- 關鍵修正：自動抓取副檔名 ---
    # 抓取上傳檔案的副檔名 (例如 .m4a 或 .mp3)
    file_ext = os.path.splitext(input_path)[1].lower()
    if not file_ext:
        file_ext = ".mp3" # 預設值
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    # 輸出檔名保持相同副檔名
    output_pattern = f"rec_{timestamp}_part%03d{file_ext}"
    
    try:
        # 執行切割
        (
            ffmpeg
            .input(input_path)
            .output(output_pattern, c='copy', f='segment', segment_time=segment_time, reset_timestamps=1)
            .run(quiet=True, overwrite_output=True)
        )
        
        # 搜尋產生的檔案
        generated_files = []
        for file in sorted(os.listdir('.')):
            # 確保只抓到這次產生的檔案，且副檔名正確
            if file.startswith(f"rec_{timestamp}") and file.endswith(file_ext):
                generated_files.append(file)
                
        return generated_files
        
    except ffmpeg.Error as e:
        st.error(f"切割失敗 (FFmpeg Error): {e.stderr.decode('utf8') if e.stderr else str(e)}")
        return []

def send_email(to_email, selected_files, sender_email, sender_password):
    """發送 Email"""
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = to_email
    msg['Subject'] = "您的音訊檔案片段"
    msg.attach(MIMEText("您好，這是您選擇的音訊切割檔案。", 'plain'))

    for filename in selected_files:
        if os.path.exists(filename):
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
        return False, f"Email 發送錯誤: {str(e)}"

# --- 使用者介面區 ---

# 添加一個重置按鈕，讓使用者可以清空狀態
if st.sidebar.button("🔄 重置所有狀態"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

uploaded_file = st.file_uploader("第一步：上傳錄音檔", type=['mp3', 'wav', 'm4a'])

if 'generated_files' not in st.session_state:
    st.session_state['generated_files'] = []

if uploaded_file is not None:
    # 取得原始檔名與副檔名
    original_ext = os.path.splitext(uploaded_file.name)[1].lower()
    temp_filename = f"temp_input{original_ext}"
    
    # 若 session 為空，執行切割
    if not st.session_state['generated_files']:
        with open(temp_filename, "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        with st.spinner(f'🚀 正在處理 {original_ext} 格式檔案...'):
            files = split_audio_ffmpeg(temp_filename)
            if files:
                st.session_state['generated_files'] = files
                st.success(f"成功！已將 {uploaded_file.name} 切割為 {len(files)} 個檔案。")
            else:
                st.warning("切割未產生檔案，請確認檔案大小是否需要切割，或格式是否正確。")
            
            # 清理暫存
            if os.path.exists(temp_filename):
                os.remove(temp_filename)

    # 顯示檔案列表
    if st.session_state['generated_files']:
        st.subheader("第二步：選擇要寄送的片段")
        
        selected_files = []
        # 檢查檔案是否真的存在於磁碟上
        valid_files = [f for f in st.session_state['generated_files'] if os.path.exists(f)]
        
        if not valid_files:
            st.error("⚠️ 找不到切割後的檔案，請按左側「重置」按鈕重新上傳。")
        else:
            for f_name in valid_files:
                file_size = os.path.getsize(f_name) / (1024 * 1024)
                # 預設勾選
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
                        # 檢查 Secrets
                        if "email" in st.secrets:
                            sender_email = st.secrets["email"]["username"]
                            sender_password = st.secrets["email"]["password"]
                            with st.spinner("寄信中..."):
                                success, msg = send_email(recipient_email, selected_files, sender_email, sender_password)
                                if success:
                                    st.balloons()
                                    st.success(msg)
                                else:
                                    st.error(msg)
                        else:
                            st.error("找不到 Email 設定，請在 Streamlit Secrets 設定 [email] 區塊。")
                    except Exception as e:
                        st.error(f"發生錯誤: {e}")
