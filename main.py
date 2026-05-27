import flet as ft
import os
from fiche import get_connection

DEP_COLORS = {
    "progress_cnc": "blue",
    "progress_welding": "orange",
    "progress_painting": "pink",
    "progress_packaging": "green"
}

def main(page: ft.Page):
    page.title = "ISO SYSTEM - تطبيق الورشة"
    page.bgcolor = "#f0f2f5" 
    page.theme_mode = ft.ThemeMode.LIGHT 
    
    # محاولة فرض الأيقونة على النافذة لجميع إصدارات Flet
    try:
        page.window.icon = "icon.png"
    except:
        page.window_icon = "icon.png"

    def show_snack(message, color="red"):
        page.snack_bar = ft.SnackBar(content=ft.Text(message, color="white", weight="bold"), bgcolor=color)
        page.snack_bar.open = True
        page.update()

    dep_dropdown = ft.Dropdown(
        label="اختر القسم",
        options=[
            ft.dropdown.Option("progress_cnc", "قسم CNC"),
            ft.dropdown.Option("progress_welding", "قسم اللحام"),
            ft.dropdown.Option("progress_painting", "قسم الصباغة"),
            ft.dropdown.Option("progress_packaging", "قسم التغليف"),
        ],
        width=280
    )

    tasks_list = ft.ListView(expand=True, spacing=15)

    def update_task(item_id, val):
        try:
            conn = get_connection()
            cur = conn.cursor()
            column = dep_dropdown.value
            cur.execute(f"UPDATE order_items SET {column} = %s WHERE item_id = %s", (val, item_id))
            conn.commit()
            cur.close()
            conn.close()
            show_snack("تم حفظ التقدّم بنجاح!", "green")
        except Exception as err:
            show_snack(f"يوجد مشكلة في الاتصال: {str(err)}", "red")

    def load_tasks(e=None):
        if not dep_dropdown.value:
            show_snack("الرجاء اختيار القسم أولاً", "red")
            return

        tasks_list.controls.clear()
        selected_color = DEP_COLORS.get(dep_dropdown.value, "blue")
        
        try:
            conn = get_connection()
            cur = conn.cursor()
            column = dep_dropdown.value
            
            cur.execute(f"SELECT item_id, customer_name, deadline, designation, dimensions, quantity, COALESCE({column}, 0), target_lames, target_profiles FROM order_items ORDER BY item_id DESC")
            rows = cur.fetchall()
            
            for row in rows:
                item_id, cust, dead_str, designation, dimensions, quantity, progress, lames, profiles = row
                
                if "Grille linéaire" in designation:
                    dims = str(dimensions).split()
                    if len(dims) >= 2:
                        total_profiles = 2 * quantity
                        profiles = f"{total_profiles} بروفيل {dims[0]} و {total_profiles} بروفيل {dims[1]}"
                
                card_content = [
                    ft.Text(f"طلب #{item_id} | {designation}", weight="bold", size=18, color=selected_color),
                    ft.Text(f"الزبون: {cust} | التسليم: {dead_str}", size=14, color="#d97706", weight="bold"),
                    ft.Divider(height=1),
                    ft.Row([
                        ft.Text(f"📏 القياس: {dimensions}", weight="bold", size=16),
                        ft.Container(width=20),
                        ft.Text(f"🛒 الكمية: {quantity}", weight="bold", size=16),
                    ], alignment=ft.MainAxisAlignment.START),
                ]
                
                if str(lames) != "0":
                    card_content.append(ft.Text(f"اللامات: {lames}", color="green", weight="bold", size=16))
                
                if str(profiles) != "0":
                    card_content.append(ft.Text(f"البروفيل: {profiles}", color="green", weight="bold", size=16))
                    
                card_content.extend([
                    ft.Text("نسبة الإنجاز:", size=14, color="grey"),
                    ft.Slider(
                        min=0, max=100, divisions=10, value=progress,
                        label="{value}%",
                        active_color=selected_color,
                        on_change=lambda e, id=item_id: update_task(id, int(e.control.value))
                    )
                ])
                
                task_card = ft.Card(
                    elevation=4,
                    content=ft.Container(
                        padding=15,
                        bgcolor="white",
                        border_radius=10,
                        content=ft.Column(card_content)
                    )
                )
                tasks_list.controls.append(task_card)

            cur.close()
            conn.close()
            page.update()
        except Exception as err:
            show_snack("الرجاء التأكد من اتصال الإنترنت أو قاعدة البيانات.", "red")

    main_layout = ft.Column(
        controls=[
            ft.Container(height=10),
            ft.Text("ISO SYSTEM - الورشة", size=24, weight="bold", color="#1e3a8a"),
            dep_dropdown,
            ft.ElevatedButton("تحديث وعرض المهام", icon="refresh", on_click=load_tasks, bgcolor="#1e3a8a", color="white"),
            tasks_list
        ],
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER
    )

    page.add(ft.SafeArea(main_layout, expand=True))

port = int(os.environ.get("PORT", 8000))
ft.app(target=main, view=ft.AppView.WEB_BROWSER, host="0.0.0.0", port=port, assets_dir="assets")