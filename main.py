import streamlit as st
import pandas as pd
import json
import re
import os
import tempfile
import csv
from datetime import datetime
from google import genai

# ================= استيراد الملفات الخارجية =================
try:
    from catalog import PRODUCT_CATALOG, calculate_materials
except ImportError:
    st.error("⚠️ ملف catalog.py مفقود. تم استخدام بيانات افتراضية.")
    PRODUCT_CATALOG = {
        "GRILLE LINEAIRE INT": {}, "GRILLE LINEAIRE EXT": {}, "PORTE FILTRE": {}, 
        "GRILLE DE REPRISE": {}, "DIFFUSEUR CARRE": {}, "CHAPEAU DE TOITURE": {}
    }
    def calculate_materials(desig, w, h, qty): return 0, "0"

try:
    from fiche import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

# ================= إعدادات الصفحة =================
st.set_page_config(page_title="ISO SYSTEM - الإدارة والتسويق", page_icon="🏢", layout="wide")

# ================= إعداد الذكاء الاصطناعي =================
MY_API_KEY = "AQ.Ab8RN6KV1Tb2fp5B3p5AZtInWCk5UcWHsxwotG_gDMu1ySeDbw"
try:
    client = genai.Client(api_key=MY_API_KEY)
except Exception as e:
    client = None

# تهيئة الذاكرة المؤقتة للطلبيات
if 'current_items' not in st.session_state:
    st.session_state.current_items = []

st.title("🏢 ISO SYSTEM - الإدارة والتسويق")
st.markdown("---")

tab_marketing, tab_dashboard = st.tabs(["🛒 إدخال الطلبيات (Marketing)", "📊 لوحة الإدارة (Dashboard)"])

# ================= 1. قسم التسويق والمدخلات =================
with tab_marketing:
    col_ai, col_manual = st.columns([1, 1])

    # --- الجزء الخاص بالذكاء الاصطناعي ---
    with col_ai:
        st.markdown("### 🤖 قراءة الفاتورة بالذكاء الاصطناعي")
        uploaded_file = st.file_uploader("اختر صورة الفاتورة أو ملف PDF", type=["png", "jpg", "jpeg", "pdf"])
        
        if uploaded_file and st.button("🚀 قراءة واستخراج البيانات", use_container_width=True, type="primary"):
            if not client:
                st.error("مفتاح الذكاء الاصطناعي غير متصل!")
            else:
                with st.spinner("جاري تحليل المستند واستخراج الطلبيات..."):
                    # حفظ الملف في السيرفر مؤقتاً
                    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{uploaded_file.name.split('.')[-1]}") as tmp:
                        tmp.write(uploaded_file.getvalue())
                        tmp_path = tmp.name

                    try:
                        ai_file = client.files.upload(file=tmp_path)
                        prompt = """
                        أنت مساعد ذكي لمدير مصنع ألمنيوم في الجزائر. قم بتحليل هذه الفاتورة أو صورة الطلبية.
                        استخرج بيانات الطلبية بدقة، واستخرج رقم الفاتورة (Proforma Invoice Number N°) واجعل النتيجة حصرياً على شكل مصفوفة JSON صالحة برمجياً، بدون أي نص إضافي.
                        التنسيق المطلوب:
                        [
                          {
                            "invoice_number": "رقم الفاتورة المستخرج بالكامل مثل 334/2026",
                            "customer": "اسم الزبون",
                            "designation": "اسم القطعة",
                            "dimensions": "القياسات (أرقام فقط مع مسافة، مثال: 400 200)",
                            "quantity": 5
                          }
                        ]
                        ملاحظات هامة جداً:
                        1- قم بتبسيط اسم القطعة. احذف الألوان والمواد (مثل ALU, BLANC, ETM). 
                        - إذا كانت القطعة "Grille linéaire" ولم يذكر أنها خارجية (Extérieur)، افترض أنها داخلية واكتبها حصراً: Grille linéaire intérieur
                        - إذا ذُكر أنها خارجية، اكتبها حصراً: Grille linéaire extérieur
                        - إذا كانت "GRILLE DE REPRISE"، اكتبها حصراً: Grille de reprise
                        2- لا تستخرج تاريخ التسليم من المستند أبداً.
                        """
                        
                        response = client.models.generate_content(model='gemini-2.5-pro', contents=[ai_file, prompt])
                        raw_text = response.text.strip()
                        
                        if raw_text.startswith("```json"):
                            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                        elif raw_text.startswith("```"):
                            raw_text = raw_text.split("```")[1].split("```")[0].strip()
                        
                        extracted_orders = json.loads(raw_text)
                        
                        for idx, order in enumerate(extracted_orders, start=1):
                            desig_raw = str(order.get("designation", "غير معروف"))
                            desig_clean = desig_raw 
                            inv_num_raw = str(order.get("invoice_number", "بدون")).strip()
                            inv_num = f"{inv_num_raw}-{idx}" if len(extracted_orders) > 1 else inv_num_raw

                            is_ext = "ext" in desig_raw.lower()
                            for cat_key in PRODUCT_CATALOG.keys():
                                cat_low = cat_key.lower()
                                if ("lineair" in desig_raw.lower() or "linéaire" in desig_raw.lower()) and ("lineair" in cat_low or "linéaire" in cat_low):
                                    if is_ext and "ext" in cat_low: desig_clean = cat_key; break
                                    elif not is_ext and "int" in cat_low: desig_clean = cat_key; break
                                    elif "ext" not in cat_low and "int" not in cat_low: desig_clean = cat_key 
                                elif "reprise" in desig_raw.lower() and "reprise" in cat_low:
                                    desig_clean = cat_key; break

                            dims_str = str(order.get("dimensions", "0"))
                            qty = int(order.get("quantity", 1))

                            dims_list = re.findall(r'\d+', dims_str)
                            w = float(dims_list[0]) if len(dims_list) > 0 else 0.0
                            h = float(dims_list[1]) if len(dims_list) > 1 else 0.0
                            
                            lames, profiles = calculate_materials(desig_clean, w, h, qty)

                            st.session_state.current_items.append({
                                "inv_num": inv_num,
                                "cust": order.get("customer", "الذكاء الاصطناعي"),
                                "entry_d": datetime.now().strftime("%Y-%m-%d"),
                                "dead_d": "غير محدد",
                                "desig": desig_clean,
                                "dims_str": dims_str,
                                "qty": qty,
                                "lames": lames,
                                "profiles": profiles
                            })
                        st.success("🤖✨ تمت قراءة المستند وإضافة الطلبيات بنجاح!")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"❌ فشل الذكاء الاصطناعي في قراءة الملف: {ex}")
                    finally:
                        if os.path.exists(tmp_path): os.remove(tmp_path)

    # --- الجزء الخاص بالإدخال اليدوي ---
    with col_manual:
        st.markdown("### ✍️ إدخال قطعة يدوياً")
        with st.form("manual_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            inv_num_input = c1.text_input("رقم الفاتورة", "INV-MANUAL")
            cust_input = c2.text_input("اسم الزبون")
            entry_date = c1.text_input("تاريخ الدخول", datetime.now().strftime("%Y-%m-%d"))
            dead_date = c2.text_input("موعد التسليم (YYYY-MM-DD)", "غير محدد")

            is_manual = st.checkbox("إدخال قطعة مخصصة (غير موجودة في الكتالوج)")
            desig_drop = st.selectbox("القطعة الجاهزة", list(PRODUCT_CATALOG.keys()))
            custom_desig = st.text_input("اسم القطعة المخصصة")

            c3, c4 = st.columns(2)
            dims_input = c3.text_input("القياسات (ex: 600 200)")
            qty_input = c4.number_input("الكمية", min_value=1, value=1)

            if st.form_submit_button("إضافة للقائمة ➕", use_container_width=True):
                actual_desig = custom_desig if is_manual else desig_drop
                if is_manual and not actual_desig:
                    st.error("يرجى كتابة اسم القطعة المخصصة")
                else:
                    dims_list = re.findall(r'\d+', str(dims_input))
                    w = float(dims_list[0]) if len(dims_list) > 0 else 0.0
                    h = float(dims_list[1]) if len(dims_list) > 1 else 0.0

                    if is_manual:
                        lames, profiles = 0, "0"
                    else:
                        lames, profiles = calculate_materials(actual_desig, w, h, qty_input)

                    exist_count = sum(1 for item in st.session_state.current_items if str(item["inv_num"]).startswith(inv_num_input))
                    final_inv = f"{inv_num_input}-{exist_count + 1}" if exist_count > 0 else inv_num_input

                    st.session_state.current_items.append({
                        "inv_num": final_inv,
                        "cust": cust_input or "غير محدد",
                        "entry_d": entry_date,
                        "dead_d": dead_date or "غير محدد",
                        "desig": actual_desig,
                        "dims_str": dims_input or "-",
                        "qty": qty_input,
                        "lames": lames,
                        "profiles": profiles
                    })
                    st.success("✅ تمت الإضافة للقائمة بنجاح!")
                    st.rerun()

    st.divider()
    st.markdown("### 📋 قائمة الطلبيات المجهزة للإرسال")
    
    if st.session_state.current_items:
        df_current = pd.DataFrame(st.session_state.current_items)
        df_current.columns = ["رقم الفاتورة", "الزبون", "دخول", "تسليم", "القطعة", "القياس", "الكمية", "لامات", "بروفيل"]
        st.dataframe(df_current, use_container_width=True)

        if st.button("🚀 إرسال جميع الطلبيات للورشة (حفظ في قاعدة البيانات)", type="primary", use_container_width=True):
            if not DB_AVAILABLE:
                st.error("قاعدة البيانات غير متصلة (تأكد من وجود fiche.py)")
            else:
                try:
                    conn = get_connection()
                    cur = conn.cursor()
                    for item in st.session_state.current_items:
                        cur.execute("""
                            INSERT INTO order_items
                            (item_id, customer_name, entry_date, deadline, designation, dimensions, quantity, target_lames, target_profiles)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (item["inv_num"], item["cust"], item["entry_d"], item["dead_d"], item["desig"], item["dims_str"], item["qty"], item["lames"], item["profiles"]))
                    conn.commit()
                    cur.close()
                    conn.close()
                    st.session_state.current_items.clear()
                    st.success("✅ تم إرسال الطلبية للورشة بنجاح!")
                    st.rerun()
                except Exception as err:
                    st.error(f"❌ خطأ أثناء الحفظ: {err}")
    else:
        st.info("لا توجد طلبيات مجهزة للإرسال حالياً.")

# ================= 2. قسم لوحة الإدارة والمتابعة =================
with tab_dashboard:
    c_title, c_ref = st.columns([8, 2])
    c_title.markdown("### 📊 لوحة الإدارة والإنتاج المباشرة")
    if c_ref.button("🔄 تحديث البيانات", use_container_width=True):
        st.rerun()

    if not DB_AVAILABLE:
        st.warning("⚠️ قاعدة البيانات غير متصلة.")
    else:
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT item_id, customer_name, deadline, designation, dimensions, quantity,
                       progress_cnc, progress_welding, progress_painting, progress_packaging, entry_date
                FROM order_items
                WHERE is_delivered = FALSE OR is_delivered IS NULL
                ORDER BY item_id DESC LIMIT 50
            """)
            db_rows = cur.fetchall()

            cur.execute("SELECT item_id, customer_name, designation, dimensions, quantity, delivered_at FROM order_items WHERE is_delivered = TRUE ORDER BY delivered_at DESC")
            delivered_rows = cur.fetchall()

            cur.close()
            conn.close()

            if db_rows:
                dash_data = []
                today = datetime.now()
                for r in db_rows:
                    item_id, cust, dead_str, desig, dims, qty, p_cnc, p_weld, p_paint, p_pack, entry_d = r

                    tole_consumption = "-"
                    if "grille" in str(desig).lower():
                        try:
                            dims_match = re.findall(r'\d+', str(dims))
                            if len(dims_match) >= 2:
                                l_cm, w_cm = float(dims_match[0])/10, float(dims_match[1])/10
                                num_lames = int(float(dims_match[1]) / 10)
                                area_lames = num_lames * ((l_cm - 1.5) * 3.2)
                                area_profiles = (2 * (((l_cm - 0.5) + 8) * 7.0)) + (2 * (((w_cm - 0.5) + 8) * 7.0))
                                tole_count = (((area_lames + area_profiles) * qty) / 20000) * 1.15
                                tole_consumption = f"{tole_count:.2f}"
                        except: pass

                    dash_data.append({
                        "رقم الفاتورة": item_id,
                        "الزبون": cust,
                        "القطعة": desig,
                        "القياس": dims,
                        "الكمية": qty,
                        "استهلاك الصاج": tole_consumption,
                        "التسليم": dead_str,
                        "CNC": f"{p_cnc or 0}%",
                        "لحام": f"{p_weld or 0}%",
                        "صباغة": f"{p_paint or 0}%",
                        "تغليف": f"{p_pack or 0}%"
                    })

                df_dash = pd.DataFrame(dash_data)

                def highlight_delayed(s):
                    try:
                        if s["التسليم"] != "غير محدد":
                            dead = datetime.strptime(str(s["التسليم"]), "%Y-%m-%d")
                            if dead < datetime.now() and float(s["تغليف"].replace('%','')) < 100:
                                return ['background-color: #fee2e2'] * len(s)
                    except: pass
                    return [''] * len(s)

                st.dataframe(df_dash.style.apply(highlight_delayed, axis=1), use_container_width=True, height=400)

                st.divider()
                c1, c2, c3 = st.columns(3)
                
                with c1:
                    st.markdown("#### 🗑️ حذف طلبية")
                    del_id = st.selectbox("اختر الفاتورة للحذف", [r[0] for r in db_rows])
                    if st.button("حذف نهائياً ❌", use_container_width=True, type="primary"):
                        conn = get_connection()
                        cur = conn.cursor()
                        cur.execute("DELETE FROM order_items WHERE item_id = %s", (del_id,))
                        conn.commit()
                        cur.close()
                        conn.close()
                        st.success(f"تم حذف {del_id} بنجاح!")
                        st.rerun()

                with c2:
                    st.markdown("#### 📥 تصدير الإكسيل (النشطة)")
                    csv_active = df_dash.to_csv(index=False, sep=';').encode('utf-8-sig')
                    st.download_button("تنزيل التقرير (Excel/CSV)", data=csv_active, file_name=f"Active_Orders_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv", use_container_width=True)

                with c3:
                    st.markdown("#### 📦 أرشيف التسليم المكتمل")
                    if delivered_rows:
                        df_arch = pd.DataFrame(delivered_rows, columns=["الفاتورة", "الزبون", "القطعة", "القياس", "الكمية", "تاريخ ووقت التسليم"])
                        csv_arch = df_arch.to_csv(index=False, sep=';').encode('utf-8-sig')
                        st.download_button("تنزيل أرشيف التسليم", data=csv_arch, file_name="Delivered_Archive.csv", mime="text/csv", use_container_width=True)
                    else:
                        st.info("لا توجد طلبيات مسلمة بعد.")
            else:
                st.info("✨ لا توجد طلبيات نشطة في الورشة حالياً.")
        except Exception as e:
            st.error(f"خطأ أثناء جلب البيانات: {e}")
