import streamlit as st
import ffmpeg
import os
import smtplib
import pandas as pd
import math
import streamlit.components.v1 as components
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime

# --- 設定頁面資訊 ---
st.set_page_config(page_title="音檔切割與寄送系統 (V11)", page_icon="📮", layout="wide")
st.title("📮 智慧音檔切割與寄送系統")
st.caption("🚀 核心 V11：新增「超過20MB自動分信寄送」與「傳輸量紀錄」。")

# 設定常數
SPLIT_LIMIT_MB = 10 
EMAIL_SIZE_LIMIT_MB = 20  # 單封信件大小上限 (MB)
LOG_FILE = "history_log.csv"

# --- 核心邏輯：永久紀錄系統 ---
def load_log():
    """從 CSV 檔案讀取歷史紀錄"""
    if os.path.exists(LOG_FILE):
        df = pd.read_csv(LOG_FILE)
        # V11 新增欄位相容性檢查：如果舊紀錄沒有「檔案總大小」，補上 NaN 或空字串
        if "檔案總大小" not in df.columns:
            df["檔案總大小"] = ""
        return df
    else:
        return pd.DataFrame(columns=["日期時間", "收件者信箱", "檔案總大小", "狀態", "詳細訊息"])

def save_log(df):
    """儲存 DataFrame 回 CSV"""
    df.to_csv(LOG_FILE, index=False)

def add_log(recipient, status, message, total_size_str):
    """寫入操作紀錄"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_data = {
        "日期時間": now,
        "收件者信箱": recipient,
        "檔案總大小": total_size_str,  # 新增欄位
        "狀態": status,
        "詳細訊息": message
    }
    df = load_log()
    df = pd.concat([pd.DataFrame([new_data]), df], ignore_index=True)
    save_log(df)
    st.session_state['mail_log_df'] = df

# --- 初始化 Session State ---
if 'mail_log_df' not in st.session_state:
    st.session_state['mail_log_df'] = load_log()
if 'last_uploaded_file_id' not in st.session_state:
    st.session_state['last_uploaded_file_id'] = None
if 'generated_files' not in st.session_state:
    st.session_state['generated_files'] = []

# --- 核心邏輯函式區 ---

def get_audio_info(file_path):
    try:
        probe = ffmpeg.probe(file_path)
        duration = float(probe['format']['duration'])
        size = float(probe['format']['size'])
        return duration, size
    except (ffmpeg.Error, KeyError, ValueError):
        return None, None

def split_audio_ffmpeg(input_path, target_size_mb=9.5):
    duration, size_bytes = get_audio_info(input_path)
    if not duration:
        st.error("❌ 檔案無法讀取或格式錯誤。")
        return []

    target_bytes = target_size_mb * 1024 * 1024
    file_ext = os.path.splitext(input_path)[1].lower()
    if not file_ext or len(file_ext) < 2: file_ext = ".mp3"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    
    # 小檔案處理
    if size_bytes <= target_bytes:
        output_name = f"rec_{timestamp}_part000{file_ext}"
        try:
            (
                ffmpeg.input(input_path).output(output_name, c='copy')
                .run(quiet=True, overwrite_output=True)
            )
            return [output_name]
        except ffmpeg.Error as e:
            st.error(f"處理失敗: {str(e)}")
            return []

    # 大檔案切割
    avg_bitrate = size_bytes / duration
    segment_time = (target_bytes / avg_bitrate) * 0.95
    output_pattern = f"rec_{timestamp}_part%03d{file_ext}"
    try:
        (
            ffmpeg.input(input_path)
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

def send_single_batch_email(to_email, batch_files, sender_email, sender_password, batch_index, total_batches):
    """發送單一封信件 (內部呼叫用)"""
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = to_email
    
    # 如果有分批，主旨加上 (第 X/Y 封)
    subject_suffix = f" ({batch_index}/{total_batches})" if total_batches > 1 else ""
    msg['Subject'] = f"您的音訊檔案片段{subject_suffix}"
    
    body = f"您好，這是您的音訊檔案。\n此為第 {batch_index} 封信，共 {total_batches} 封。"
    msg.attach(MIMEText(body, 'plain'))

    for filename in batch_files:
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
        return True, "成功"
    except Exception as e:
        return False, str(e)

# ==========================================
#              介面佈局 (Tabs)
# ==========================================

tab1, tab2 = st.tabs(["👤 使用者模式 (切割與寄信)", "🔐 管理員後台 (紀錄維護)"])

# ------------------------------------------
# TAB 1: 一般使用者功能
# ------------------------------------------
with tab1:
    with st.sidebar:
        st.header("⚙️ 工具")
        if st.button("🔄 清除重來 (Start Over)", type="primary"):
            st.session_state['generated_files'] = []
            st.session_state['last_uploaded_file_id'] = None
            st.rerun()
        st.info("💡 **提示：**\n點擊上方按鈕可重新開始。\n歷史紀錄將永久保存。")

    # 上傳區
    uploaded_file = st.file_uploader(f"第一步：上傳錄音檔 (若超過 {SPLIT_LIMIT_MB}MB 將自動分割)", type=None)

    if uploaded_file is not None:
        current_file_id = f"{uploaded_file.name}-{uploaded_file.size}"
        if st.session_state['last_uploaded_file_id'] != current_file_id:
            st.session_state['generated_files'] = []
            st.session_state['last_uploaded_file_id'] = current_file_id 
        
        original_ext = os.path.splitext(uploaded_file.name)[1].lower()
        if not original_ext: original_ext = ".mp3"
        temp_filename = f"temp_input{original_ext}"
        
        if not st.session_state['generated_files']:
            with open(temp_filename, "wb") as f:
                f.write(uploaded_file.getbuffer())   
            msg = f'🚀 檔案較大，正在分割 {uploaded_file.name} ...' if uploaded_file.size > SPLIT_LIMIT_MB * 1024 * 1024 else f'🚀 正在處理 {uploaded_file.name} ...'
            with st.spinner(msg):
                files = split_audio_ffmpeg(temp_filename, target_size_mb=SPLIT_LIMIT_MB - 0.5)
                if files:
                    st.session_state['generated_files'] = files
                    st.success(f"處理完成！")
                if os.path.exists(temp_filename):
                    os.remove(temp_filename)

    # 寄送設定區
    if st.session_state['generated_files']:
        st.divider()
        valid_files = [f for f in st.session_state['generated_files'] if os.path.exists(f)]
        
        if not valid_files:
            st.warning("⚠️ 檔案已清除，請按左側「清除重來」按鈕。")
        else:
            col1, col2 = st.columns([1, 1])
            with col1:
                st.subheader("第二步：選擇檔案")
                selected_files = []
                for f_name in valid_files:
                    file_size = os.path.getsize(f_name) / (1024 * 1024)
                    if st.checkbox(f"{f_name} ({file_size:.2f} MB)", value=True):
                        selected_files.append(f_name)
                
                # 計算選擇檔案的總大小
                total_selected_size_mb = sum([os.path.getsize(f) for f in selected_files]) / (1024 * 1024)
                st.caption(f"📊 已選取總大小：{total_selected_size_mb:.2f} MB")

            with col2:
                # 需求 2：新增文字說明
                st.subheader("第三步：寄送設定")
                st.markdown(f"⚠️ **注意：單封郵件附件上限 {EMAIL_SIZE_LIMIT_MB}MB。**\n若選取總量超過上限，系統將自動拆分為多封信件寄出。")
                recipient_email = st.text_input("收件者信箱", placeholder="name@example.com")
                
                if st.button("🚀 確認寄送檔案", type="primary", use_container_width=True):
                    if not recipient_email:
                        st.warning("⚠️ 請輸入 Email")
                    elif not selected_files:
                        st.warning("⚠️ 請選擇檔案")
                    else:
                        status_container = st.status("🚀 系統運作中...", expanded=True)
                        try:
                            # 停止按鈕
                            stop_button_html = """
                                <style>
                                    .stop-btn { background-color: #ff4b4b; color: white; padding: 10px; border: none; border-radius: 8px; cursor: pointer; width: 100%; font-weight: bold;}
                                    .stop-btn:hover { background-color: #ff0000; }
                                </style>
                                <button class="stop-btn" onclick="window.parent.location.reload();">🛑 強制停止 (STOP)</button>
                            """
                            with status_container:
                                components.html(stop_button_html, height=60)

                            if "email" in st.secrets:
                                sender_email = st.secrets["email"]["username"]
                                sender_password = st.secrets["email"]["password"]
                                
                                # --- 核心邏輯：自動分信算法 (Auto-Batching) ---
                                batches = []
                                current_batch = []
                                current_batch_size = 0
                                size_limit_bytes = EMAIL_SIZE_LIMIT_MB * 1024 * 1024
                                
                                # 貪婪演算法分配檔案
                                for file in selected_files:
                                    f_size = os.path.getsize(file)
                                    # 如果單個檔案加上去會爆，就先把目前的這批打包
                                    if current_batch_size + f_size > size_limit_bytes:
                                        if current_batch: # 確保有東西才打包
                                            batches.append(current_batch)
                                            current_batch = []
                                            current_batch_size = 0
                                    
                                    current_batch.append(file)
                                    current_batch_size += f_size
                                
                                # 把最後剩下的也打包
                                if current_batch:
                                    batches.append(current_batch)
                                
                                # 開始迴圈寄送
                                total_batches = len(batches)
                                status_container.write(f"📦 檔案總大，自動拆分為 {total_batches} 封信件發送...")
                                
                                all_success = True
                                error_msgs = []
                                
                                for i, batch in enumerate(batches):
                                    idx = i + 1
                                    status_container.write(f"📤 正在寄送第 {idx}/{total_batches} 封信 (含 {len(batch)} 個檔案)...")
                                    success, msg = send_single_batch_email(recipient_email, batch, sender_email, sender_password, idx, total_batches)
                                    if not success:
                                        all_success = False
                                        error_msgs.append(f"第 {idx} 封失敗: {msg}")
                                        status_container.error(f"❌ 第 {idx} 封寄送失敗！")
                                
                                # 紀錄結果
                                total_size_str = f"{total_selected_size_mb:.2f} MB"
                                
                                if all_success:
                                    status_container.update(label="✅ 所有信件寄送成功！", state="complete", expanded=False)
                                    st.balloons()
                                    add_log(recipient_email, "🟢 成功", f"共 {total_batches} 封，全數送達", total_size_str)
                                else:
                                    status_container.update(label="⚠️ 部分或全部失敗", state="error", expanded=True)
                                    final_msg = " | ".join(error_msgs)
                                    st.error(f"傳送結果：{final_msg}")
                                    add_log(recipient_email, "🟠 部分失敗", final_msg, total_size_str)

                            else:
                                status_container.update(label="❌ 設定錯誤", state="error")
                                st.error("Secrets 設定遺失")
                                add_log(recipient_email, "🔴 設定錯誤", "Secrets 未設定", "0 MB")
                        except Exception as e:
                            status_container.update(label="❌ 中斷/錯誤", state="error")
                            add_log(recipient_email, "⚫ 中斷/錯誤", "使用者手動終止或連線錯誤", "未知")

    # 底部顯示紀錄
    st.divider()
    st.subheader("📋 寄送歷史紀錄 (唯讀)")
    df_read = load_log()
    st.dataframe(df_read, use_container_width=True, hide_index=True)


# ------------------------------------------
# TAB 2: 管理員後台
# ------------------------------------------
with tab2:
    st.header("🔐 管理員登入")
    admin_password = st.text_input("請輸入管理員密碼", type="password")
    
    is_admin = False
    if "admin" in st.secrets:
        if admin_password == st.secrets["admin"]["password"]:
            is_admin = True
        elif admin_password:
            st.error("❌ 密碼錯誤")
    else:
        st.warning("⚠️ 請先在 Secrets 設定 [admin] 密碼")

    if is_admin:
        st.success("✅ 登入成功！")
        st.divider()
        st.subheader("📝 紀錄編輯器")
        st.info("💡 提示：修改後請點擊下方紅色按鈕儲存。")
        
        current_df = load_log()
        edited_df = st.data_editor(
            current_df,
            num_rows="dynamic",
            use_container_width=True,
            key="history_editor"
        )
        
        if st.button("💾 儲存所有變更 (Save Changes)", type="primary"):
            save_log(edited_df)
            st.session_state['mail_log_df'] = edited_df 
            st.success("🎉 資料庫已更新！")
            st.rerun()
