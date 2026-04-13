import tkinter as tk
from tkinter import messagebox
import sys
import os
import winreg
from datetime import datetime, timedelta
import threading
import time
import winsound

ALARM_INTERVAL_SECONDS = 3600  # 테스트용 1분, 운영 시 3600으로 변경

class DailyReporter:
    def __init__(self, root):
        self.root = root
        self.root.title("Daily Reporter")
        self.root.geometry("320x290")
        self.root.resizable(False, False)
        self.root.configure(bg="#f5f5f5")

        try:
            if hasattr(sys, '_MEIPASS'):
                icon_path = os.path.join(sys._MEIPASS, 'icon.ico')
            else:
                icon_path = 'icon.ico'
            self.root.iconbitmap(icon_path)
        except Exception:
            pass

        self.alarm_running = False
        self._log_file_mtime = None
        self.open_popups = []

        # 커스텀 메뉴바
        menubar_frame = tk.Frame(root, bg="#f5f5f5")
        menubar_frame.pack(fill="x", side="top")

        self.autostart_var = tk.BooleanVar(value=self.get_autostart())

        settings_dropdown = tk.Menu(
            root, tearoff=0,
            bg="#f5f5f5", fg="#333333",
            activebackground="#e0e0e0", activeforeground="#333333",
            relief="flat", bd=1
        )
        settings_dropdown.add_checkbutton(
            label="윈도우 시작 시 자동 실행",
            variable=self.autostart_var,
            command=self.toggle_autostart
        )

        def show_settings(event=None):
            btn = settings_btn
            settings_dropdown.tk_popup(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height())

        settings_btn = tk.Button(
            menubar_frame, text="설정",
            font=("Segoe UI", 9),
            bg="#f5f5f5", fg="#555555",
            activebackground="#e0e0e0", activeforeground="#333333",
            relief="flat", cursor="hand2", padx=8, pady=3, bd=0,
            command=show_settings
        )
        settings_btn.pack(side="left")

        log_btn = tk.Button(
            menubar_frame, text="로그 확인",
            font=("Segoe UI", 9),
            bg="#f5f5f5", fg="#555555",
            activebackground="#e0e0e0", activeforeground="#333333",
            relief="flat", cursor="hand2", padx=8, pady=3, bd=0,
            command=self.open_log_file
        )
        log_btn.pack(side="left")

        # 실시간 시계
        self.clock_label = tk.Label(
            root,
            text="",
            font=("Segoe UI", 20, "bold"),
            bg="#f5f5f5",
            fg="#222222"
        )
        self.clock_label.pack(pady=(20, 4))
        self.update_clock()

        # 출근/퇴근 버튼 프레임
        btn_frame = tk.Frame(root, bg="#f5f5f5")
        btn_frame.pack(pady=10)

        self.start_button = tk.Button(
            btn_frame, text="출근", command=self.start_day,
            width=10, height=2,
            font=("Segoe UI", 11, "bold"),
            bg="#4CAF50", fg="white",
            activebackground="#45a049", activeforeground="white",
            relief="flat", cursor="hand2"
        )
        self.start_button.pack(side="left", padx=10)

        self.end_button = tk.Button(
            btn_frame, text="퇴근", command=self.end_day,
            width=10, height=2,
            font=("Segoe UI", 11, "bold"),
            bg="#e0e0e0", fg="#aaaaaa",
            activebackground="#cccccc", activeforeground="#aaaaaa",
            relief="flat", cursor="arrow",
            state="disabled"
        )
        self.end_button.pack(side="left", padx=10)

        # 상태 라벨
        self.status_label = tk.Label(
            root, text="출근 전",
            font=("Segoe UI", 10),
            bg="#f5f5f5", fg="#888888"
        )
        self.status_label.pack(pady=(6, 2))

        # 구분선
        separator = tk.Frame(root, height=1, bg="#dddddd")
        separator.pack(fill="x", padx=20, pady=6)

        # 마지막 기록 표시
        tk.Label(
            root, text="마지막 기록",
            font=("Segoe UI", 8),
            bg="#f5f5f5", fg="#aaaaaa"
        ).pack()

        self.last_log_label = tk.Label(
            root, text="-",
            font=("Segoe UI", 9, "bold"),
            bg="#f5f5f5", fg="#555555",
            wraplength=280, justify="center"
        )
        self.last_log_label.pack(pady=(2, 0))

        self.copy_button = tk.Button(
            root, text="복사", command=self.copy_last_log,
            font=("Segoe UI", 8),
            bg="#e0e0e0", fg="#555555",
            activebackground="#cccccc", activeforeground="#333333",
            relief="flat", cursor="hand2", width=6
        )
        self.copy_button.pack(pady=(4, 0))

        # 서명
        self.signature_label = tk.Label(
            root,
            text="@ 2026 Made by YKJ",
            font=("Segoe UI", 8),
            bg="#f5f5f5", fg="#cccccc"
        )
        self.signature_label.place(relx=1.0, rely=1.0, anchor='se', x=-5, y=-5)

        self.poll_log_file()

    REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    REG_NAME = "DailyReporter"

    def get_autostart(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.REG_KEY, 0, winreg.KEY_READ) as key:
                winreg.QueryValueEx(key, self.REG_NAME)
            return True
        except OSError:
            return False

    def toggle_autostart(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
                if self.autostart_var.get():
                    winreg.SetValueEx(key, self.REG_NAME, 0, winreg.REG_SZ, f'"{sys.executable}"')
                else:
                    try:
                        winreg.DeleteValue(key, self.REG_NAME)
                    except FileNotFoundError:
                        pass
        except OSError:
            messagebox.showerror("오류", "자동 실행 설정에 실패했습니다.")
            self.autostart_var.set(not self.autostart_var.get())

    def poll_log_file(self):
        filename = self.get_today_filename()
        if os.path.exists(filename):
            mtime = os.path.getmtime(filename)
            if mtime != self._log_file_mtime:
                self._log_file_mtime = mtime
                with open(filename, 'r', encoding='utf-8') as f:
                    lines = [l.rstrip() for l in f.readlines() if l.strip()]
                self.last_log_label.config(text=lines[-1] if lines else "-")
        elif self._log_file_mtime is not None:
            self._log_file_mtime = None
            self.last_log_label.config(text="-")
        self.root.after(5000, self.poll_log_file)

    def open_log_file(self):
        filename = self.get_today_filename()
        if not os.path.exists(filename):
            messagebox.showinfo("알림", "오늘 기록된 파일이 없습니다.")
            return
        os.startfile(filename)

    def update_clock(self):
        self.clock_label.config(text=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.root.after(1000, self.update_clock)

    def get_today_filename(self):
        today = datetime.now().strftime("%Y-%m-%d")
        if hasattr(sys, '_MEIPASS'):
            exec_dir = os.path.dirname(sys.executable)
        else:
            exec_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(exec_dir, f"{today}.txt")

    def copy_last_log(self):
        text = self.last_log_label.cget("text")
        if text == "-":
            return
        # 타임스탬프(YYYY-MM-DD HH:MM:SS = 19자) 이후 내용만 복사
        content = text[20:].strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(content)

    def write_log(self, text):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        filename = self.get_today_filename()
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(f"{now} {text}\n")
        self._log_file_mtime = os.path.getmtime(filename)
        self.last_log_label.config(text=f"{now} {text}")

    def start_day(self):
        if not self.alarm_running:
            self.write_log("출근")
            self.alarm_running = True
            self.start_button.config(state="disabled", bg="#cccccc", fg="#aaaaaa", cursor="arrow")
            self.end_button.config(state="normal", bg="#f44336", fg="white",
                                   activebackground="#e53935", activeforeground="white", cursor="hand2")
            self.status_label.config(text="열일중!", fg="#f44336")
            threading.Thread(target=self.hourly_alarm, daemon=True).start()

    def auto_end_day(self):
        self.alarm_running = False
        for popup in self.open_popups[:]:
            try:
                popup.destroy()
            except Exception:
                pass
        self.open_popups.clear()
        self.write_log("퇴근 (자동)")
        self.root.after(500, self.root.destroy)

    def end_day(self):
        self.alarm_running = False
        self.write_log("퇴근")
        self.start_button.config(state="normal", bg="#4CAF50", fg="white",
                                 activebackground="#45a049", activeforeground="white", cursor="hand2")
        self.end_button.config(state="disabled", bg="#e0e0e0", fg="#aaaaaa",
                               activebackground="#cccccc", activeforeground="#aaaaaa", cursor="arrow")
        self.status_label.config(text="퇴근 완료", fg="#888888")

    def hourly_alarm(self):
        while self.alarm_running:
            now = datetime.now()
            next_hour = (now + timedelta(seconds=ALARM_INTERVAL_SECONDS)).replace(minute=0, second=0, microsecond=0)
            sleep_duration = (next_hour - now).total_seconds()
            time.sleep(sleep_duration)
            if self.alarm_running:
                self.root.after(0, self.show_alarm_popup)

    def show_alarm_popup(self):
        if len(self.open_popups) >= 4:
            self.auto_end_day()
            return

        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)

        popup = tk.Toplevel()
        self.open_popups.append(popup)
        popup.title("정시 기록")
        popup.geometry("320x170")
        popup.resizable(False, False)
        popup.configure(bg="#f5f5f5")
        popup.attributes('-topmost', True)

        current_time = datetime.now().replace(minute=0, second=0, microsecond=0)

        tk.Label(
            popup,
            text=current_time.strftime("%Y-%m-%d %H:%M"),
            font=("Segoe UI", 14, "bold"),
            bg="#f5f5f5", fg="#222222"
        ).pack(pady=(16, 6))

        entry = tk.Entry(popup, width=36, font=("Segoe UI", 10), relief="solid", bd=1)
        entry.pack(pady=4, padx=20)
        entry.focus_set()

        def on_popup_close():
            if popup in self.open_popups:
                self.open_popups.remove(popup)
            popup.destroy()

        popup.protocol("WM_DELETE_WINDOW", on_popup_close)

        def save_entry(event=None):
            content = entry.get().strip()
            if content:
                filename = self.get_today_filename()
                log_text = f"{current_time.strftime('%Y-%m-%d %H:%M:%S')} {content}"
                with open(filename, 'a', encoding='utf-8') as f:
                    f.write(f"{log_text}\n")
                self._log_file_mtime = os.path.getmtime(filename)
                self.last_log_label.config(text=log_text)
                if popup in self.open_popups:
                    self.open_popups.remove(popup)
                popup.destroy()
            else:
                messagebox.showwarning("입력 필요", "기록할 내용을 입력하세요.")

        popup.bind("<Return>", save_entry)

        tk.Button(
            popup, text="기록", command=save_entry,
            font=("Segoe UI", 10, "bold"),
            bg="#4CAF50", fg="white",
            activebackground="#45a049", activeforeground="white",
            relief="flat", cursor="hand2", width=12
        ).pack(pady=12)

if __name__ == '__main__':
    root = tk.Tk()
    app = DailyReporter(root)
    root.mainloop()
