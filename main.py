import streamlit as st
import os
import re
import requests
from datetime import datetime

# ================= 1. محاولة استيراد قاعدة البيانات =================
try:
    from fiche import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

# ================= 2. إعدادات الصفحة والأقسام =================
st.set_page_config(page_title="ISO SYSTEM - الورشة", page_icon="👷", layout="centered")

DEP_COLORS = {
    "progress_cnc": "blue",
    "progress_bending": "purple", 
    "progress_welding": "orange",
    "progress_painting": "pink",
    "progress_packaging": "green",
    "progress_delivery": "teal"  
}

DEPARTMENTS_DATA = {
    "progress_cnc": {"name": "قسم CNC", "password": "etm001"},
    "progress_bending": {"name": "قسم الثني", "password": "etm123"},
    "progress_welding": {"name": "قسم اللحام", "password": "etm567"},
    "progress_painting": {"name": "قسم الصباغة", "password": "etm003"},
    "progress_packaging": {"name": "قسم التغليف", "password": "etm004"},
    "progress_delivery": {"name": "قسم التسليم (Livraison)", "password": "etm111"} 
}

SPECIAL_PARTS = ["eclisse", "esclise", "chemin", "câble", "cable", "collier", "colie", "rail"]

# ================= 3. إعدادات إشعارات تيليغرام =================
TELEGRAM_BOT_TOKEN = "8739784371:AAG1nNf74pGvUW62ylr6KRY01pM2QkoQIWw" 
TELEGRAM_CHAT_ID = "5019932770"   

def send_telegram_notification(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: 
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=data, timeout=5)
    except Exception as e:
        print("Telegram Error:", e)

# ================= 4. إدارة حالة الجلسة (Session State) =================
if 'auth_dept' not in st.session_state:
    st.session_state.auth_dept = None

# ================= 5. دوال قاعدة البيانات والتحديث =================
def update_progress(item_id, column, slider_key):
    new_val = st.session_state[slider_key]
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(f"UPDATE order_items SET {column} = %s WHERE item_id = %s", (new_val, str(item_id)))
        conn.commit()
        cur.close()
        conn.close()
        st.toast("✅ تم حفظ التقدم بنجاح!", icon="✅")
    except Exception as e:
        st.error(f"خطأ في الاتصال: {e}")

def mark_as_delivered_group(item_ids_list, invoice_number, customer_name):
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_connection()
        cur = conn.cursor()
        for i_id in item_ids_list:
            cur.execute("UPDATE order_items SET is_delivered = TRUE, delivered_at = %s WHERE item_id = %s", (now_str, str(i_id)))
        conn.commit()
        cur.close()
        cur.close()
        conn.close()
        
        msg = f"📦 *تم تسليم طلبية بنجاح!*\n\n🧾 الفاتورة: `{invoice_number}`\n👤 الزبون: *{customer_name}*\n🕒 الوقت: {now_str}"
        send_telegram_notification(msg)
        
        st.success("📦 تم تأكيد تسليم الفاتورة وإرسال إشعار للإدارة!")
    except Exception as e:
        st.error(f"حدث خطأ أثناء التحديث: {e}")

# ================= 6. واجهة تسجيل الدخول =================
if st.session_state.auth_dept is None:
    st.markdown("<h1 style='text-align: center; color: #1e3a8a;'>ISO SYSTEM - تطبيق الورشة</h1>", unsafe_allow_html=True)
    st.markdown("---")
    
    with st.container():
        st.markdown("### 🔐 تسجيل الدخول للقسم")
        dept_options = list(DEPARTMENTS_DATA.keys())
        dept_labels = [DEPARTMENTS_DATA[k]["name"] for k in dept_options]
        
        selected_dept_label = st.selectbox("اختر القسم", dept_labels)
        selected_key = dept_options[dept_labels.index(selected_dept_label)]
        
        password = st.text_input("الرمز السري", type="password")
        
        if st.button("دخول 🚀", use_container_width=True, type="primary"):
            if password == DEPARTMENTS_DATA[selected_key]["password"]:
                st.session_state.auth_dept = selected_key
                st.rerun()
            else:
                st.error("❌ الرمز السري خاطئ!")

# ================= 7. واجهة مهام القسم المفتوح =================
else:
    current_dept = st.session_state.auth_dept
    dept_name = DEPARTMENTS_DATA[current_dept]["name"]
    
    col1, col2 = st.columns([8, 2])
    with col1:
        st.markdown(f"<h2 style='color: #1e3a8a;'>👷 {dept_name}</h2>", unsafe_allow_html=True)
    with col2:
        if st.button("🚪 خروج"):
            st.session_state.auth_dept = None
            st.rerun()
            
    st.markdown("---")
    
    if not DB_AVAILABLE:
        st.error("⚠️ ملف قاعدة البيانات `fiche.py` غير متصل!")
        st.stop()

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT item_id, customer_name, deadline, designation, dimensions, quantity, target_lames, target_profiles, 
                   progress_cnc, progress_bending, progress_bending_profiles, progress_welding, progress_painting, progress_packaging 
            FROM order_items 
            WHERE is_delivered = FALSE OR is_delivered IS NULL 
            ORDER BY item_id DESC
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        displayed_tasks = 0

        # ================= نظام قسم التسليم (Livraison) =================
        if current_dept == "progress_delivery":
            grouped_orders = {}
            for row in rows:
                item_id, cust, dead_str, designation, dimensions, quantity, lames, profiles, p_cnc, p_bend_lames, p_bend_profs, p_weld, p_paint, p_pack = row
                try:
                    pack_val = float(p_pack or 0.0)
                    if pack_val < 100: continue
                except: pass
                
                base_inv_id = re.sub(r'-\d+$', '', str(item_id))
                if base_inv_id not in grouped_orders:
                    grouped_orders[base_inv_id] = {
                        "customer": cust, "deadline": dead_str, "items_details": [], "item_ids": []
                    }
                grouped_orders[base_inv_id]["items_details"].append(f"▪ {designation} | القياس: {dimensions} | الكمية: {quantity}")
                grouped_orders[base_inv_id]["item_ids"].append(item_id)
                displayed_tasks += 1
                
            for base_id, data in grouped_orders.items():
                with st.container(border=True):
                    st.subheader(f"🧾 فاتورة / طلبية # {base_id}")
                    st.markdown(f"**الزبون:** :orange[{data['customer']}] | **التسليم:** :orange[{data['deadline']}]")
                    st.divider()
                    st.markdown("**محتويات الفاتورة الجاهزة للتسليم:**")
                    for item_text in data["items_details"]:
                        st.write(item_text)
                    st.write("")
                    if st.button("📦 تأكيد تسليم الفاتورة بالكامل (Livré)", key=f"btn_deliv_{base_id}", type="primary", use_container_width=True):
                        mark_as_delivered_group(data["item_ids"], base_id, data['customer'])
                        st.rerun()
                        
            if displayed_tasks == 0:
                st.info("🎉 لا توجد فواتير جاهزة للتسليم حالياً.")

        # ================= نظام باقي الأقسام (الإنتاج) =================
        else:
            for row in rows:
                item_id, cust, dead_str, designation, dimensions, quantity, lames, profiles, p_cnc, p_bend_lames, p_bend_profs, p_weld, p_paint, p_pack = row
                
                try:
                    pack_val = float(p_pack or 0.0)
                    if pack_val >= 100: continue 
                except: pass

                desig_lower = str(designation).lower()
                is_special_part = any(sp in desig_lower for sp in SPECIAL_PARTS)
                if is_special_part and current_dept not in ["progress_cnc", "progress_bending"]:
                    continue 

                has_lames = str(lames) not in ["0", "None", "", "0.0"]
                has_profiles = str(profiles) not in ["0", "None", "", "0.0"]

                if designation and "Grille linéaire" in designation:
                    dims = str(dimensions).split()
                    if len(dims) >= 2:
                        total_profiles = 2 * quantity
                        profiles = f"{total_profiles} بروفيل {dims[0]} و {total_profiles} بروفيل {dims[1]}"
                        has_profiles = True

                displayed_tasks += 1
                progress_dict = {"progress_cnc": p_cnc, "progress_welding": p_weld, "progress_painting": p_paint, "progress_packaging": p_pack}

                with st.container(border=True):
                    st.markdown(f"#### ⚙️ قطعة #{item_id} | {designation}")
                    st.markdown(f"**الزبون:** :orange[{cust}] | **التسليم:** :orange[{dead_str}]")
                    st.markdown(f"📏 **القياس:** `{dimensions}` &nbsp;&nbsp; | &nbsp;&nbsp; 🛒 **الكمية:** `{quantity}`")
                    
                    if current_dept in ["progress_cnc", "progress_bending"]:
                        if has_lames: st.success(f"الامـات: {lames}")
                        if has_profiles: st.info(f"البروفيل: {profiles}")

                    if current_dept == "progress_bending":
                        if has_lames:
                            k = f"bend_l_{item_id}"
                            st.slider("نسبة ثني اللامات:", 0, 100, int(p_bend_lames or 0), step=10, key=k, on_change=update_progress, args=(item_id, "progress_bending", k))
                        if has_profiles:
                            k = f"bend_p_{item_id}"
                            st.slider("نسبة ثني البروفيل:", 0, 100, int(p_bend_profs or 0), step=10, key=k, on_change=update_progress, args=(item_id, "progress_bending_profiles", k))
                        if not has_lames and not has_profiles:
                            k = f"bend_{item_id}"
                            st.slider("نسبة الإنجاز:", 0, 100, int(p_bend_lames or 0), step=10, key=k, on_change=update_progress, args=(item_id, "progress_bending", k))
                    else:
                        main_progress = int(progress_dict.get(current_dept) or 0)
                        k = f"{current_dept}_{item_id}"
                        st.slider("نسبة الإنجاز:", 0, 100, main_progress, step=10, key=k, on_change=update_progress, args=(item_id, current_dept, k))
            
            if displayed_tasks == 0:
                st.info("🎉 لا توجد مهام حالياً لهذا القسم. عمل رائع!")

    except Exception as e:
        st.error(f"⚠️ خطأ في قراءة البيانات. يرجى التأكد من أن قاعدة البيانات مهيأة. ({e})")