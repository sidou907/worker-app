import flet as ft
import os
import re
import requests
import threading
from datetime import datetime
from fiche import get_connection

# ================= 1. إعدادات الأقسام، الألوان، وكلمات المرور =================
DEP_COLORS = {
    "progress_cnc": "blue",
    "progress_bending": "purple", 
    "progress_welding": "orange",
    "progress_painting": "pink",
    "progress_packaging": "green",
    "progress_delivery": "teal"  
}

DEPARTMENTS_DATA = {
    "progress_cnc": {"name": "قسم CNC", "password": "cutting1998521"},
    "progress_bending": {"name": "قسم الثني", "password": "bending2026"},
    "progress_welding": {"name": "قسم اللحام", "password": "soudeur2000"},
    "progress_painting": {"name": "قسم الصباغة", "password": "painting2030"},
    "progress_packaging": {"name": "قسم التغليف", "password": "packaging2030"},
    "progress_delivery": {"name": "قسم التسليم (Livraison)", "password": "livre2026"} 
}

SPECIAL_PARTS = ["eclisse", "esclise", "chemin", "câble", "cable", "collier", "colie", "rail"]

# ================= 2. إعدادات إشعارات تيليغرام =================
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
# ===============================================================

def main(page: ft.Page):
    page.title = "ISO SYSTEM - تطبيق الورشة"
    page.bgcolor = "#f0f2f5" 
    page.theme_mode = ft.ThemeMode.LIGHT 
    
    try:
        page.rtl = True
        page.window.icon = "icon.png"
    except:
        pass

    def show_snack(message, color="red"):
        snack = ft.SnackBar(content=ft.Text(message, color="white", weight="bold"), bgcolor=color, duration=4000)
        page.overlay.append(snack)
        snack.open = True
        page.update()

    authenticated_dept = [None] 

    dep_dropdown = ft.Dropdown(
        label="اختر القسم",
        options=[
            ft.dropdown.Option("progress_cnc", "قسم CNC"),
            ft.dropdown.Option("progress_bending", "قسم الثني"), 
            ft.dropdown.Option("progress_welding", "قسم اللحام"),
            ft.dropdown.Option("progress_painting", "قسم الصباغة"),
            ft.dropdown.Option("progress_packaging", "قسم التغليف"),
            ft.dropdown.Option("progress_delivery", "قسم التسليم (Livraison)"), 
        ],
        width=280
    )

    password_input = ft.TextField(
        label="أدخل الرمز السري", password=True, can_reveal_password=True, text_align=ft.TextAlign.CENTER
    )

    def close_dialog_action():
        password_dialog.open = False
        password_input.value = ""
        page.update()

    def verify_password(e):
        selected_key = dep_dropdown.value
        if not selected_key:
            return show_snack("الرجاء اختيار القسم أولاً", "red")
            
        correct_password = DEPARTMENTS_DATA[selected_key]["password"]
        
        if password_input.value == correct_password:
            authenticated_dept[0] = selected_key 
            close_dialog_action()
            actual_load_tasks() 
            show_snack(f"✅ تم الدخول إلى {DEPARTMENTS_DATA[selected_key]['name']}", "green")
        else:
            show_snack("❌ الرمز السري خاطئ!", "red")

    password_dialog = ft.AlertDialog(
        title=ft.Text("تأكيد الصلاحية", weight="bold"),
        content=password_input,
        actions=[
            ft.TextButton("دخول", on_click=verify_password),
            ft.TextButton("إلغاء", on_click=lambda e: close_dialog_action())
        ]
    )

    tasks_list = ft.ListView(expand=True, spacing=15)

    def update_task(item_id, val, column_to_update):
        try:
            conn = get_connection()
            cur = conn.cursor()
            # حماية item_id ليُقرأ كنص متوافق مع الفواتير الجديدة
            cur.execute(f"UPDATE order_items SET {column_to_update} = %s WHERE item_id = %s", (val, str(item_id)))
            conn.commit()
            cur.close()
            conn.close()
            show_snack("تم حفظ التقدّم بنجاح!", "green")
        except Exception as err:
            show_snack(f"يوجد مشكلة في الاتصال: {str(err)}", "red")

    def mark_as_delivered_group(item_ids_list, invoice_number, customer_name):
        try:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn = get_connection()
            cur = conn.cursor()
            for i_id in item_ids_list:
                cur.execute("UPDATE order_items SET is_delivered = TRUE, delivered_at = %s WHERE item_id = %s", (now_str, str(i_id)))
            conn.commit()
            cur.close()
            conn.close()
            
            msg = f"📦 *تم تسليم طلبية بنجاح!*\n\n🧾 الفاتورة: `{invoice_number}`\n👤 الزبون: *{customer_name}*\n🕒 الوقت: {now_str}"
            threading.Thread(target=send_telegram_notification, args=(msg,), daemon=True).start()

            show_snack("📦 تم تأكيد تسليم الفاتورة وتم إرسال إشعار للإدارة!", "green")
            actual_load_tasks() 
        except Exception as err:
            show_snack(f"حدث خطأ أثناء التحديث: {str(err)}", "red")

    def try_load_tasks(e=None):
        if not dep_dropdown.value:
            show_snack("الرجاء اختيار القسم أولاً", "red")
            return
        
        if dep_dropdown.value != authenticated_dept[0]:
            if password_dialog not in page.overlay:
                page.overlay.append(password_dialog)
            password_dialog.open = True
            page.update()
        else:
            actual_load_tasks()

    def actual_load_tasks():
        tasks_list.controls.clear()
        selected_color = DEP_COLORS.get(dep_dropdown.value, "blue")
        current_column = dep_dropdown.value
        
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
            
            displayed_tasks_count = 0

            # ================= 1. نظام قسم التسليم =================
            if current_column == "progress_delivery":
                grouped_orders = {} 
                
                for row in rows:
                    item_id, cust, dead_str, designation, dimensions, quantity, lames, profiles, p_cnc, p_bend_lames, p_bend_profs, p_weld, p_paint, p_pack = row
                    
                    try:
                        pack_val = float(p_pack) if p_pack and str(p_pack).strip() != "" else 0.0
                        if pack_val < 100: continue 
                    except: pass
                    
                    base_inv_id = re.sub(r'-\d+$', '', str(item_id))
                    
                    if base_inv_id not in grouped_orders:
                        grouped_orders[base_inv_id] = {
                            "customer": cust,
                            "deadline": dead_str,
                            "items_details": [],
                            "item_ids": []
                        }
                    
                    grouped_orders[base_inv_id]["items_details"].append(f"▪ {designation} | القياس: {dimensions} | الكمية: {quantity}")
                    grouped_orders[base_inv_id]["item_ids"].append(item_id)
                    displayed_tasks_count += 1
                
                for base_id, data in grouped_orders.items():
                    card_content = [
                        ft.Text(f"فاتورة / طلبية # {base_id}", weight="bold", size=22, color=selected_color),
                        ft.Text(f"الزبون: {data['customer']} | التسليم: {data['deadline']}", size=14, color="#d97706", weight="bold"),
                        ft.Divider(height=1),
                        ft.Text("محتويات الفاتورة الجاهزة للتسليم:", color="grey", size=14, weight="bold")
                    ]
                    
                    for item_text in data["items_details"]:
                        card_content.append(ft.Text(item_text, size=16, weight="bold"))
                    
                    card_content.append(ft.Container(height=10))
                    card_content.append(
                        ft.ElevatedButton(
                            content=ft.Text("📦 تأكيد تسليم الفاتورة بالكامل (Livré)", weight="bold", color="white", size=16),
                            bgcolor="#10b981", 
                            height=48,
                            on_click=lambda e, ids=data["item_ids"], inv=base_id, cust=data['customer']: mark_as_delivered_group(ids, inv, cust)
                        )
                    )
                    
                    task_card = ft.Card(elevation=4, content=ft.Container(padding=15, bgcolor="white", border_radius=10, content=ft.Column(card_content)))
                    tasks_list.controls.append(task_card)

            # ================= 2. نظام باقي الأقسام =================
            else:
                for row in rows:
                    item_id, cust, dead_str, designation, dimensions, quantity, lames, profiles, p_cnc, p_bend_lames, p_bend_profs, p_weld, p_paint, p_pack = row
                    
                    try:
                        pack_val = float(p_pack) if p_pack and str(p_pack).strip() != "" else 0.0
                        if pack_val >= 100: continue 
                    except: pass 

                    desig_lower = str(designation).lower()
                    is_special_part = any(sp in desig_lower for sp in SPECIAL_PARTS)

                    if is_special_part and current_column not in ["progress_cnc", "progress_bending"]:
                        continue 

                    displayed_tasks_count += 1

                    has_lames = str(lames) not in ["0", "None", "", "0.0"]
                    has_profiles = str(profiles) not in ["0", "None", "", "0.0"]

                    if designation and "Grille linéaire" in designation:
                        dims = str(dimensions).split()
                        if len(dims) >= 2:
                            total_profiles = 2 * quantity
                            profiles = f"{total_profiles} بروفيل {dims[0]} و {total_profiles} بروفيل {dims[1]}"
                            has_profiles = True
                    
                    card_content = [
                        ft.Text(f"قطعة #{item_id} | {designation}", weight="bold", size=18, color=selected_color),
                        ft.Text(f"الزبون: {cust} | التسليم: {dead_str}", size=14, color="#d97706", weight="bold"),
                        ft.Divider(height=1),
                        ft.Row([
                            ft.Text(f"📏 القياس: {dimensions}", weight="bold", size=16),
                            ft.Container(width=20),
                            ft.Text(f"🛒 الكمية: {quantity}", weight="bold", size=16),
                        ], alignment=ft.MainAxisAlignment.START),
                    ]
                    
                    if current_column in ["progress_cnc", "progress_bending"]:
                        if has_lames: card_content.append(ft.Text(f"الامـات: {lames}", color="green", weight="bold", size=16))
                        if has_profiles: card_content.append(ft.Text(f"البروفيل: {profiles}", color="green", weight="bold", size=16))
                        
                    progress_dict = {"progress_cnc": p_cnc, "progress_welding": p_weld, "progress_painting": p_paint, "progress_packaging": p_pack}
                    
                    if current_column == "progress_bending":
                        if has_lames:
                            card_content.append(ft.Text("نسبة ثني اللامات:", size=14, color="grey"))
                            card_content.append(ft.Slider(min=0, max=100, divisions=10, value=float(p_bend_lames or 0), label="{value}%", active_color=selected_color, on_change_end=lambda e, id=item_id: update_task(id, int(e.control.value), "progress_bending")))
                        if has_profiles:
                            card_content.append(ft.Text("نسبة ثني البروفيل:", size=14, color="grey"))
                            card_content.append(ft.Slider(min=0, max=100, divisions=10, value=float(p_bend_profs or 0), label="{value}%", active_color=selected_color, on_change_end=lambda e, id=item_id: update_task(id, int(e.control.value), "progress_bending_profiles")))
                        if not has_lames and not has_profiles:
                            card_content.append(ft.Text("نسبة الإنجاز:", size=14, color="grey"))
                            card_content.append(ft.Slider(min=0, max=100, divisions=10, value=float(p_bend_lames or 0), label="{value}%", active_color=selected_color, on_change_end=lambda e, id=item_id: update_task(id, int(e.control.value), "progress_bending")))
                    else:
                        main_progress = float(progress_dict.get(current_column) or 0)
                        card_content.append(ft.Text("نسبة الإنجاز:", size=14, color="grey"))
                        card_content.append(ft.Slider(min=0, max=100, divisions=10, value=main_progress, label="{value}%", active_color=selected_color, on_change_end=lambda e, id=item_id, col=current_column: update_task(id, int(e.control.value), col)))
                    
                    task_card = ft.Card(elevation=4, content=ft.Container(padding=15, bgcolor="white", border_radius=10, content=ft.Column(card_content)))
                    tasks_list.controls.append(task_card)

            if displayed_tasks_count == 0:
                tasks_list.controls.append(ft.Row(controls=[ft.Text("لا توجد مهام حالياً لهذا القسم 🎉", size=18, color="grey", weight="bold")], alignment=ft.MainAxisAlignment.CENTER))

            page.update()
        except Exception as err:
            error_msg = str(err)
            if "relation" in error_msg and "does not exist" in error_msg:
                show_snack("⚠️ قاعدة البيانات فارغة! يجب تشغيل init_db.py أولاً", "red")
            else:
                show_snack(f"الخطأ هو: {error_msg}", "red")

    main_layout = ft.Column(
        controls=[
            ft.Container(height=10),
            ft.Text("ISO SYSTEM - الورشة", size=24, weight="bold", color="#1e3a8a"),
            dep_dropdown,
            ft.ElevatedButton(content=ft.Text("🔄 تحديث وعرض المهام", color="white", weight="bold"), on_click=try_load_tasks, bgcolor="#1e3a8a"),
            tasks_list
        ],
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER
    )

    page.add(ft.SafeArea(main_layout, expand=True))

if __name__ == "__main__":
    ft.app(target=main)