import customtkinter as ctk
import serial
import serial.tools.list_ports
import json
import os
import time
import threading
from tkinter import messagebox, filedialog

# ================= КАРТА КЛАВИШ =================
KEY_MAP = {
    "НЕТ": 0,
    "A": 97, "B": 98, "C": 99, "D": 100, "E": 101, "F": 102, "G": 103, "H": 104, 
    "I": 105, "J": 106, "K": 107, "L": 108, "M": 109, "N": 110, "O": 111, "P": 112, 
    "Q": 113, "R": 114, "S": 115, "T": 116, "U": 117, "V": 118, "W": 119, "X": 120, 
    "Y": 121, "Z": 122, 
    "1": 49, "2": 50, "3": 51, "4": 52, "5": 53, "6": 54, "7": 55, "8": 56, "9": 57, "0": 48,
    "ENTER": 176, "ESC": 177, "BACKSPACE": 178, "TAB": 179, "SPACE": 32,
    "LEFT_CTRL": 128, "LEFT_SHIFT": 129, "LEFT_ALT": 130, "LEFT_GUI": 131,
    "RIGHT_CTRL": 132, "RIGHT_SHIFT": 133, "RIGHT_ALT": 134, "RIGHT_GUI": 135,
    "UP": 218, "DOWN": 217, "LEFT": 216, "RIGHT": 215,
    "F1": 194, "F2": 195, "F3": 196, "F4": 197, "F5": 198,
    "MEDIA_PLAY": 205, "VOL_UP": 206, "VOL_DOWN": 207, "MUTE": 208,
    "NEXT_TRACK": 209, "PREV_TRACK": 210
}
KEY_MAP_REV = {v: k for k, v in KEY_MAP.items()}
ACTION_TYPES = {"Нажать": "press", "Отпустить": "release", "Ждать": "delay"}
ACTION_TYPES_REV = {v: k for k, v in ACTION_TYPES.items()}

class MacroPadPro(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("MacroPad PRO v7.0 (Ultimate)")
        self.geometry("1150x850")
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        
        self.serial_port = None
        self.current_btn_index = 0
        self.recording_widget = None
        self.recording_mode = None
        
        # Папка для профилей
        self.profiles_dir = "profiles"
        if not os.path.exists(self.profiles_dir):
            os.makedirs(self.profiles_dir)
        
        self.buttons_data = [{"mode": 0, "actions": []} for _ in range(6)]
        
        self.bind("<Key>", self.on_key_press)
        self.setup_ui()
        self.scan_ports()
        self.load_profiles_list()

    def setup_ui(self):
        # === ЛЕВАЯ ПАНЕЛЬ ===
        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        
        ctk.CTkLabel(self.sidebar, text="MACROPAD v7.0", font=("Arial Black", 20)).pack(pady=(20, 10))
        
        # --- Секция ПРОФИЛИ ---
        p_frame = ctk.CTkFrame(self.sidebar, fg_color="#2B2B2B")
        p_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(p_frame, text="📁 ПРОФИЛИ", font=("Arial", 12, "bold")).pack(pady=5)
        
        self.profile_combo = ctk.CTkComboBox(p_frame, values=["Нет профилей"])
        self.profile_combo.pack(fill="x", padx=10, pady=5)
        
        p_btns = ctk.CTkFrame(p_frame, fg_color="transparent")
        p_btns.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(p_btns, text="Загрузить", width=80, command=self.load_profile_btn).pack(side="left", padx=2)
        ctk.CTkButton(p_btns, text="Сохранить", width=80, command=self.save_profile_btn).pack(side="left", padx=2)
        ctk.CTkButton(p_btns, text="🗑️", width=30, fg_color="#CD5C5C", command=self.delete_profile_btn).pack(side="right", padx=2)

        # --- Секция ПОДКЛЮЧЕНИЕ ---
        c_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        c_frame.pack(fill="x", padx=10, pady=20)
        ctk.CTkLabel(c_frame, text="USB ПОРТ:", font=("Arial", 12, "bold")).pack(anchor="w")
        
        port_row = ctk.CTkFrame(c_frame, fg_color="transparent")
        port_row.pack(fill="x", pady=5)
        
        self.port_combo = ctk.CTkComboBox(port_row, width=170, values=["Поиск..."])
        self.port_combo.pack(side="left")
        
        # Кнопка ОБНОВИТЬ ПОРТЫ
        ctk.CTkButton(port_row, text="🔄", width=40, command=self.scan_ports).pack(side="right", padx=5)
        
        self.connect_btn = ctk.CTkButton(c_frame, text="ПОДКЛЮЧИТЬ", fg_color="#2CC985", 
                                         font=("Arial", 13, "bold"), command=self.toggle_connection)
        self.connect_btn.pack(fill="x", pady=10)
        
        self.status_lbl = ctk.CTkLabel(self.sidebar, text="Не подключено", text_color="gray")
        self.status_lbl.pack(side="bottom", pady=5)

        # Кнопка ЗАПИСИ
        self.upload_btn = ctk.CTkButton(self.sidebar, text="ЗАПИСАТЬ В ПАМЯТЬ", state="disabled", 
                                        fg_color="#F72585", height=50, font=("Arial", 14, "bold"),
                                        command=self.upload_config)
        self.upload_btn.pack(side="bottom", pady=20, padx=15, fill="x")

        # === ЦЕНТРАЛЬНАЯ ЧАСТЬ ===
        self.main_area = ctk.CTkFrame(self, fg_color="transparent")
        self.main_area.pack(side="right", fill="both", expand=True, padx=20, pady=20)
        
        # --- МАТРИЦА 3x2 ---
        ctk.CTkLabel(self.main_area, text="ФИЗИЧЕСКИЕ КНОПКИ", font=("Arial", 14, "bold")).pack(anchor="w")
        matrix = ctk.CTkFrame(self.main_area)
        matrix.pack(fill="x", pady=10)
        
        self.btn_widgets = []
        labels = ["1", "2", "3", "4", "5", "6"]
        for i in range(6):
            btn = ctk.CTkButton(matrix, text=labels[i], width=100, height=70, font=("Arial", 20, "bold"),
                                fg_color="transparent", border_width=2, border_color="gray40",
                                command=lambda x=i: self.select_button(x))
            btn.grid(row=i//3, column=i%3, padx=20, pady=15)
            self.btn_widgets.append(btn)

        # --- РЕДАКТОР ---
        self.editor_frame = ctk.CTkFrame(self.main_area, fg_color="transparent")
        self.editor_frame.pack(fill="both", expand=True)
        
        self.lbl_title = ctk.CTkLabel(self.editor_frame, text="Настройка Кнопки 1", font=("Arial", 24))
        self.lbl_title.pack(anchor="w", pady=(0, 10))

        self.tab_view = ctk.CTkTabview(self.editor_frame)
        self.tab_view.pack(fill="both", expand=True)
        
        self.tab_hold = self.tab_view.add("🎮 УДЕРЖАНИЕ")
        self.tab_macro = self.tab_view.add("⚡ МАКРОС")
        
        # Вкладка HOLD
        h_f = ctk.CTkFrame(self.tab_hold, fg_color="transparent")
        h_f.pack(expand=True)
        self.btn_record_hold = ctk.CTkButton(h_f, text="НАЖАТЬ ДЛЯ ВЫБОРА", width=250, height=60, 
                                           fg_color="#343638", font=("Arial", 16, "bold"),
                                           command=lambda: self.start_recording(self.btn_record_hold, "hold"))
        self.btn_record_hold.pack(pady=20)
        self.hold_key_label = ctk.CTkLabel(h_f, text="Назначено: НЕТ", font=("Arial", 20, "bold"), text_color="#2CC985")
        self.hold_key_label.pack()

        # Вкладка MACRO
        # Панель инструментов
        t_f = ctk.CTkFrame(self.tab_macro, fg_color="transparent")
        t_f.pack(fill="x", pady=5)
        ctk.CTkButton(t_f, text="+ Действие", width=100, command=self.add_macro_row).pack(side="left", padx=5)
        ctk.CTkButton(t_f, text="Очистить", width=80, fg_color="#CD5C5C", command=self.clear_macro).pack(side="left", padx=5)
        
        # БЫСТРАЯ ВСТАВКА
        q_f = ctk.CTkFrame(self.tab_macro, fg_color="#2B2B2B", height=40)
        q_f.pack(fill="x", pady=5)
        ctk.CTkLabel(q_f, text="Быстро:", font=("Arial", 11)).pack(side="left", padx=10)
        presets = [("Ctrl+C", self.p_copy), ("Ctrl+V", self.p_paste), ("Ctrl+Z", self.p_undo), ("Win+D", self.p_wind)]
        for name, func in presets:
            ctk.CTkButton(q_f, text=name, width=60, height=24, fg_color="#404040", command=func).pack(side="left", padx=2)

        self.macro_scroll = ctk.CTkScrollableFrame(self.tab_macro)
        self.macro_scroll.pack(fill="both", expand=True, pady=10)

        # --- НАСТРОЙКИ ---
        sett = ctk.CTkFrame(self.main_area, height=80)
        sett.pack(fill="x", pady=10)
        
        ctk.CTkLabel(sett, text="Яркость:", font=("Arial", 12, "bold")).pack(side="left", padx=15)
        self.slider_bri = ctk.CTkSlider(sett, from_=0, to=50, number_of_steps=50, command=self.on_brightness_change)
        self.slider_bri.set(150)
        self.slider_bri.pack(side="left", fill="x", expand=True, padx=10)
        
        ctk.CTkLabel(sett, text="Сон (мин):", font=("Arial", 12, "bold")).pack(side="left", padx=10)
        self.slider_sleep = ctk.CTkSlider(sett, from_=0, to=30, number_of_steps=30, command=self.on_sleep_change)
        self.slider_sleep.set(5)
        self.slider_sleep.pack(side="left", fill="x", expand=True, padx=10)
        self.lbl_sleep = ctk.CTkLabel(sett, text="5 мин", width=50)
        self.lbl_sleep.pack(side="left")

        self.select_button(0)

    # ================== ЛОГИКА ==================
    def scan_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo.configure(values=ports if ports else ["Нет устройств"])
        if ports: self.port_combo.set(ports[0])

    def toggle_connection(self):
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            self.serial_port = None
            self.connect_btn.configure(text="ПОДКЛЮЧИТЬ", fg_color="#2CC985")
            self.upload_btn.configure(state="disabled")
            self.status_lbl.configure(text="Отключено", text_color="gray")
            self.port_combo.configure(state="normal")
        else:
            try:
                self.serial_port = serial.Serial(self.port_combo.get(), 115200, timeout=1)
                time.sleep(2) # Reset delay
                
                # Check connection
                self.serial_port.write(b'\n')
                self.serial_port.write(json.dumps({"cmd": "ping"}).encode() + b'\n')
                resp = self.serial_port.readline().decode(errors='ignore')
                
                if "ping" in resp:
                    self.connect_btn.configure(text="ОТКЛЮЧИТЬ", fg_color="#CD5C5C")
                    self.upload_btn.configure(state="normal")
                    self.status_lbl.configure(text="ПОДКЛЮЧЕНО", text_color="#2CC985")
                    self.port_combo.configure(state="disabled")
                    self.read_device_config() # AUTO READ
                else:
                    self.serial_port.close()
                    messagebox.showwarning("Ошибка", "Устройство не отвечает.\nПроверьте, горит ли светодиод постоянно.")
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))

    def on_brightness_change(self, val):
        # Отправляем яркость в реальном времени
        if self.serial_port and self.serial_port.is_open:
            try:
                cmd = {"cmd": "set_settings", "brightness": int(val)}
                self.serial_port.write(json.dumps(cmd).encode() + b'\n')
            except: pass

    def on_sleep_change(self, val):
        self.lbl_sleep.configure(text=f"{int(val)} мин" if val > 0 else "Выкл")

    def read_device_config(self):
        try:
            self.status_lbl.configure(text="ЧТЕНИЕ...", text_color="orange")
            self.update()
            self.serial_port.reset_input_buffer()
            self.serial_port.write(json.dumps({"cmd": "get_config"}).encode() + b'\n')
            
            start = time.time()
            while time.time() - start < 5:
                line = self.serial_port.readline().decode(errors='ignore').strip()
                if not line or not line.startswith("{"): continue
                
                try:
                    data = json.loads(line)
                    cmd = data.get("cmd")
                    if cmd == "config_data":
                        self.slider_bri.set(data.get("bri", 150))
                        self.slider_sleep.set(data.get("sleep", 300000) / 60000)
                        self.on_sleep_change(self.slider_sleep.get())
                    elif cmd == "macro_data":
                        idx = data.get("btn")
                        if 0 <= idx < 6:
                            self.buttons_data[idx]["mode"] = data.get("mode", 0)
                            self.buttons_data[idx]["actions"] = data.get("actions", [])
                    elif cmd == "config_end":
                        break
                except: pass
            
            self.status_lbl.configure(text="ГОТОВО", text_color="#2CC985")
            self.select_button(self.current_btn_index)
        except Exception as e:
            self.status_lbl.configure(text="ОШИБКА ЧТЕНИЯ", text_color="red")

    def upload_config(self):
        self.save_current_ui_to_data()
        if not self.serial_port: return
        try:
            # Send settings
            s_cmd = {"cmd": "set_settings", "brightness": int(self.slider_bri.get()), "sleep": int(self.slider_sleep.get())*60000}
            self.serial_port.write(json.dumps(s_cmd).encode() + b'\n')
            time.sleep(0.1)
            
            # Send macros
            for i, d in enumerate(self.buttons_data):
                m_cmd = {"cmd": "set_macro", "button": i, "mode": d["mode"], "actions": d["actions"]}
                self.serial_port.write(json.dumps(m_cmd).encode() + b'\n')
                time.sleep(0.1)
            
            # Save
            self.serial_port.write(json.dumps({"cmd": "save"}).encode() + b'\n')
            messagebox.showinfo("Успех", "Записано! Устройство перезагружается.")
            self.toggle_connection()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    # --- UI Helpers ---
    def select_button(self, index):
        self.save_current_ui_to_data()
        self.current_btn_index = index
        self.lbl_title.configure(text=f"Настройка КНОПКИ {index+1}")
        for i, btn in enumerate(self.btn_widgets):
            btn.configure(fg_color="#3B8ED0" if i == index else "transparent", border_color="#3B8ED0" if i == index else "gray40")
        self.load_button_data(index)

    def load_button_data(self, index):
        data = self.buttons_data[index]
        if data["mode"] == 1:
            self.tab_view.set("🎮 УДЕРЖАНИЕ")
            key = "НЕТ"
            for a in data["actions"]:
                if a["t"] == "press":
                    key = KEY_MAP_REV.get(a["k"], "НЕТ")
                    break
            self.hold_key_label.configure(text=f"Назначено: {key}")
        else:
            self.tab_view.set("⚡ МАКРОС")
            self.clear_macro()
            for a in data["actions"]:
                self.add_macro_row(a["t"], a["k"], a["v"])

    def save_current_ui_to_data(self):
        idx = self.current_btn_index
        if self.tab_view.get() == "🎮 УДЕРЖАНИЕ":
            self.buttons_data[idx]["mode"] = 1
        else:
            self.buttons_data[idx]["mode"] = 0
            acts = []
            for row in self.macro_scroll.winfo_children():
                if hasattr(row, 'widgets'):
                    t = row.widgets['type'].get()
                    k = row.widgets['key_code']
                    try: v = int(row.widgets['val'].get())
                    except: v = 0
                    acts.append({"t": ACTION_TYPES.get(t, "press"), "k": k, "v": v})
            self.buttons_data[idx]["actions"] = acts

    # --- Recording ---
    def start_recording(self, widget, mode, index=None):
        self.recording_widget = widget
        self.recording_mode = mode
        self.recording_index = index # для макросов
        widget.configure(text="⌨️ НАЖМИТЕ КЛАВИШУ...", fg_color="#E0A526")
        self.focus_set()

    def on_key_press(self, event):
        if not self.recording_widget: return
        k = event.keysym.upper()
        tk_map = {"RETURN": "ENTER", "CONTROL_L": "LEFT_CTRL", "CONTROL_R": "RIGHT_CTRL", "SHIFT_L": "LEFT_SHIFT", "SHIFT_R": "RIGHT_SHIFT", "ALT_L": "LEFT_ALT", "ALT_R": "RIGHT_ALT", "SUPER_L": "LEFT_GUI", "SUPER_R": "RIGHT_GUI"}
        if k in tk_map: k = tk_map[k]
        if len(k) == 1: k = k.upper()

        if k in KEY_MAP:
            if self.recording_mode == "hold":
                self.buttons_data[self.current_btn_index]["actions"] = [{"t": "press", "k": KEY_MAP[k], "v": 0}]
                self.hold_key_label.configure(text=f"Назначено: {k}")
                self.recording_widget.configure(text="НАЖАТЬ ДЛЯ ВЫБОРА", fg_color="#343638")
            elif self.recording_mode == "macro":
                # Только обновляем текст кнопки, данные сохранятся при переключении
                row = self.macro_scroll.winfo_children()[self.recording_index]
                if hasattr(row, 'key_btn'):
                    row.key_btn.configure(text=k)
                    row.widgets['key_code'] = KEY_MAP[k]
        else:
            self.recording_widget.configure(text="НЕ ПОДДЕРЖИВАЕТСЯ", fg_color="#CD5C5C")
            self.after(500, lambda: self.recording_widget.configure(text="ВЫБРАТЬ", fg_color="#343638"))
        self.recording_widget = None

    def add_macro_row(self, type_val="press", key_code=0, delay=0):
        row = ctk.CTkFrame(self.macro_scroll, height=45)
        row.pack(fill="x", pady=2)
        
        cb = ctk.CTkComboBox(row, values=["Нажать", "Отпустить", "Ждать"], width=90)
        cb.set(ACTION_TYPES_REV.get(type_val, "Нажать"))
        cb.pack(side="left", padx=5)
        
        k_name = KEY_MAP_REV.get(key_code, "ВЫБРАТЬ")
        idx = len(self.macro_scroll.winfo_children()) - 1
        btn = ctk.CTkButton(row, text=k_name, width=120, fg_color="#2B2B2B", command=lambda: self.start_recording(btn, "macro", idx))
        btn.pack(side="left", padx=5)
        
        ent = ctk.CTkEntry(row, width=60)
        if delay > 0: ent.insert(0, str(delay))
        ent.pack(side="left")
        
        ctk.CTkButton(row, text="✕", width=30, fg_color="#CD5C5C", command=lambda: [row.destroy(), self.reindex()]).pack(side="right", padx=5)
        row.key_btn = btn
        row.widgets = {'type': cb, 'key_code': key_code, 'val': ent}

    def reindex(self):
        for i, row in enumerate(self.macro_scroll.winfo_children()):
             if hasattr(row, 'key_btn'):
                 row.key_btn.configure(command=lambda w=row.key_btn, idx=i: self.start_recording(w, "macro", idx))

    def clear_macro(self):
        for w in self.macro_scroll.winfo_children(): w.destroy()

    # --- PROFILES ---
    def load_profiles_list(self):
        files = [f.replace(".json", "") for f in os.listdir(self.profiles_dir) if f.endswith(".json")]
        self.profile_combo.configure(values=files if files else ["Нет профилей"])

    def save_profile_btn(self):
        self.save_current_ui_to_data()
        name = ctk.CTkInputDialog(text="Введите имя профиля:", title="Сохранить").get_input()
        if name:
            path = os.path.join(self.profiles_dir, f"{name}.json")
            data = {"buttons": self.buttons_data, "bri": self.slider_bri.get(), "slp": self.slider_sleep.get()}
            with open(path, "w") as f: json.dump(data, f)
            self.load_profiles_list()
            self.profile_combo.set(name)

    def load_profile_btn(self):
        name = self.profile_combo.get()
        path = os.path.join(self.profiles_dir, f"{name}.json")
        if os.path.exists(path):
            with open(path, "r") as f:
                data = json.load(f)
                self.buttons_data = data["buttons"]
                self.slider_bri.set(data.get("bri", 150))
                self.slider_sleep.set(data.get("slp", 5))
                self.on_sleep_change(self.slider_sleep.get())
                self.select_button(self.current_btn_index)

    def delete_profile_btn(self):
        name = self.profile_combo.get()
        path = os.path.join(self.profiles_dir, f"{name}.json")
        if os.path.exists(path):
            os.remove(path)
            self.load_profiles_list()
            self.profile_combo.set("Нет профилей")

    # --- PRESETS ---
    def p_add(self, keys):
        for k in keys: self.add_macro_row("press", KEY_MAP[k], 0)
        self.add_macro_row("delay", 0, 50)
        for k in reversed(keys): self.add_macro_row("release", KEY_MAP[k], 0)
    
    def p_copy(self): self.p_add(["LEFT_CTRL", "C"])
    def p_paste(self): self.p_add(["LEFT_CTRL", "V"])
    def p_undo(self): self.p_add(["LEFT_CTRL", "Z"])
    def p_wind(self): self.p_add(["LEFT_GUI", "D"])

if __name__ == "__main__":
    app = MacroPadPro()
    app.mainloop()