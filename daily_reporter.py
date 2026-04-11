import tkinter as tk
from tkinter import messagebox
import sys
import os
from datetime import datetime, timedelta
import threading
import time
import winsound

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

        # 서명
        self.signature_label = tk.Label(
            root,
            text="@ 2026 Made by YKJ",
            font=("Segoe UI", 8),
            bg="#f5f5f5", fg="#cccccc"
        )
        self.signature_label.place(relx=1.0, rely=1.0, anchor='se', x=-5, y=-5)

    def update_clock(self):
        self.clock_label.config(text=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.root.after(1000, self.update_clock)

    def get_today_filename(self):
        today = datetime.now().strftime("%Y-%m-%d")
        exec_dir = os.getcwd()
        return os.path.join(exec_dir, f"{today}.txt")

    def write_log(self, text):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        filename = self.get_today_filename()
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(f"{now} {text}\n")
        self.last_log_label.config(text=f"{now}  {text}")

    def start_day(self):
        if not self.alarm_running:
            self.write_log("출근")
            self.alarm_running = True
            self.start_button.config(state="disabled", bg="#cccccc", fg="#aaaaaa", cursor="arrow")
            self.end_button.config(state="normal", bg="#f44336", fg="white",
                                   activebackground="#e53935", activeforeground="white", cursor="hand2")
            self.status_label.config(text="열일중!", fg="#f44336")
            threading.Thread(target=self.hourly_alarm, daemon=True).start()

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
            next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            sleep_duration = (next_hour - now).total_seconds()
            time.sleep(sleep_duration)
            if self.alarm_running:
                self.root.after(0, self.show_alarm_popup)

    def show_alarm_popup(self):
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)

        popup = tk.Toplevel()
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

        def save_entry(event=None):
            content = entry.get().strip()
            if content:
                filename = self.get_today_filename()
                log_text = f"{current_time.strftime('%Y-%m-%d %H:%M:%S')} {content}"
                with open(filename, 'a', encoding='utf-8') as f:
                    f.write(f"{log_text}\n")
                self.last_log_label.config(text=log_text)
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
