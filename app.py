import streamlit as st
import ffmpeg
import os
import smtplib
import pandas as pd  # 新增：用於製作紀錄表
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime

# 設定頁面資訊
st.set_page_config(page_title="音檔切割與寄送系統 (專業版)", page_icon="📮", layout="wide")
st.title("📮 智慧音檔切割與寄送系統")
st.caption("🚀 核心 V4：新增「即時狀態監控」與「寄送歷史紀錄」。")

# --- 初始化 Session State (紀錄表單) ---
if 'mail_log' not in st.session_state:
    # 初始化一個空的列表來存紀錄
    st.session_state['mail_log'] = []

def add_log(recipient, status, message):
    """將操作紀錄寫入 Session State"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state['mail_log'].insert(0, {
        "日期時間": now,
        "收件者信箱": recipient,
        "狀態": status,
        "詳細訊息": message
    })

# --- 核心邏輯函式區 ---

def get_audio_info(file_path):
    """獲取音訊資訊"""
    try:
        probe = ffmpeg.probe(file_path)
        duration = float(probe['format']['duration'])
        size = float(probe['format']['size'])
        return duration, size
    except (ffmpeg.Error, KeyError, ValueError):
        return None, None

def split_audio_ffmpeg(input_path, target_size_mb=9.5):
    """切割音訊"""
    duration, size_bytes = get_audio_info(input_path)
    if not duration:
        return []

    target_bytes = target_size_mb * 1024 * 1024
    if size_bytes <= target_bytes:
        return [input_path]

    avg_bitrate = size_bytes / duration
    segment_time = (target_bytes / avg_bitrate) * 0.95
    
    file_ext = os.path.splitext(input_path)[1].lower()
    if not file_ext or len(file_ext) < 2:
        file_ext = ".mp3"
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_pattern = f"rec_{timestamp}_part%03d{file_ext}"
    
    try:
        (
            ffmpeg
            .input(input_path)
            .output(output_pattern, c='copy', f='segment', segment_time=segment_time, reset_timestamps=1)
            .run(quiet=True, overwrite_output=True)
        )
        generated_files = []
        for file in sorted(os.listdir('.')):
            if file.startswith(f"rec_{timestamp}") and file.endswith(file_ext):
                generated_files.append(file)
        return generated_files
    except ffmpeg.Error as e:
        st.error(f"切割失敗: {str(e)}")
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
        return False, f"錯誤: {str(e)}"

# --- 使用者介面區 ---

# 側邊欄：重置與說明
with st.sidebar:
    st.header("⚙️ 設定與工具")
    if st.button("🗑️ 清空所有歷史紀錄"):
        st.session_state['mail_log'] = []
        st.rerun()
    
    if st.button("🔄 重置上傳狀態"):
        if 'generated_files' in st.session_state:
            del st.session_state['generated_files']
        st.rerun()
        
    st.info("💡 **關於停止鍵：**\n由於網頁傳輸限制，一旦開始寄送，介面會顯示轉圈圈。若要**強制終止**，請直接重新整理網頁 (F5) 或點擊瀏覽器的停止載入按鈕。紀錄表將會捕捉到失敗或中斷前的狀態。")

# 主介面
uploaded_file = st.file_uploader("第一步：上傳錄音檔 (支援手機/電腦)", type=None)

if 'generated_files' not in st.session_state:
    st.session_state['generated_files'] = []

# 切割邏輯
if uploaded_file is not None:
    original_ext = os.path.splitext(uploaded_file.name)[1].lower()
    if not original_ext: original_ext = ".mp3"
    temp_filename = f"temp_input{original_ext}"
    
    if not st.session_state['generated_files']:
        with open(temp_filename, "wb") as f:
            f.write(uploaded_file.getbuffer())   
        with st.spinner(f'🚀 正在切割 {uploaded_file.name} ...'):
            files = split_audio_ffmpeg(temp_filename)
            if files:
                st.session_state['generated_files'] = files
                st.success(f"切割完成！共 {len(files)} 個檔案。")
            if os.path.exists(temp_filename):
                os.remove(temp_filename)

# 寄送與紀錄邏輯
if st.session_state['generated_files']:
    st.divider()
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("第二步：選擇檔案")
        selected_files = []
        valid_files = [f for f in st.session_state['generated_files'] if os.path.exists(f)]
        for f_name in valid_files:
            file_size = os.path.getsize(f_name) / (1024 * 1024)
            if st.checkbox(f"{f_name} ({file_size:.2f} MB)", value=True):
                selected_files.append(f_name)

    with col2:
        st.subheader("第三步：寄送設定")
        recipient_email = st.text_input("收件者信箱", placeholder="name@example.com")
        
        # 這裡使用 st.status 建立一個可視化的狀態框
        if st.button("🚀 確認寄送檔案", type="primary", use_container_width=True):
            if not recipient_email:
                st.warning("⚠️ 請輸入 Email")
            elif not selected_files:
                st.warning("⚠️ 請選擇檔案")
            else:
                # 開始寄送流程
                status_container = st.status("正在連線郵件伺服器...", expanded=True)
                try:
                    if "email" in st.secrets:
                        sender_email = st.secrets["email"]["username"]
                        sender_password = st.secrets["email"]["password"]
                        
                        status_container.write("📤 正在上傳附件並傳送中...")
                        
                        # 執行寄信
                        success, msg = send_email(recipient_email, selected_files, sender_email, sender_password)
                        
                        if success:
                            status_container.update(label="✅ 寄送成功！", state="complete", expanded=False)
                            st.balloons()
                            add_log(recipient_email, "🟢 成功", "檔案已寄出")
                        else:
                            status_container.update(label="❌ 寄送失敗", state="error", expanded=True)
                            st.error(msg)
                            add_log(recipient_email, "🔴 失敗", msg)
                    else:
                        status_container.update(label="❌ 設定錯誤", state="error")
                        st.error("找不到 Secrets 設定")
                        add_log(recipient_email, "🔴 設定錯誤", "找不到 Secrets")
                        
                except Exception as e:
                    status_container.update(label="❌ 發生意外錯誤", state="error")
                    st.error(f"系統錯誤: {e}")
                    add_log(recipient_email, "⚫ 中斷/錯誤", str(e))

# --- 歷史紀錄顯示區 (Requirement 2) ---
st.divider()
st.subheader("📋 寄送歷史紀錄表")

if st.session_state['mail_log']:
    # 將 log 轉換為 DataFrame 表格
    df_log = pd.DataFrame(st.session_state['mail_log'])
    
    # 使用 dataframe 顯示，並針對「狀態」欄位做簡單的顏色標示 (Streamlit 自動處理)
    st.dataframe(
        df_log, 
        use_container_width=True,
        column_config={
            "日期時間": st.column_config.TextColumn("日期時間", width="medium"),
            "狀態": st.column_config.TextColumn("狀態", width="small"),
            "詳細訊息": st.column_config.TextColumn("詳細訊息", width="large"),
        }
    )
else:
    st.info("尚無寄送紀錄。")
