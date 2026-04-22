import tkinter as tk
from tkinter import messagebox
import sys
import os
import re
import json
import zipfile
import shutil
import winreg
from collections import OrderedDict
from datetime import datetime, timedelta
import threading
import time
import winsound

ALARM_INTERVAL_SECONDS = 3600

# 템플릿(유타렉스 일일업무보고_양기정_26_04_16.hwpx) 고정 구조
_TMPL_DATE      = "2026년 04월 16일"
_TMPL_CHECKIN   = "09:00:00"
_TMPL_CHECKOUT  = "18:00:00"
_TMPL_WORKHOURS = " 8시간"
_TMPL_TIMES = [
    "09:00~10:00", "10:00~11:00", "11:00~12:30",
    "12:30~13:30", "13:30~14:00", "14:00~15:00",
    "15:00~16:00", "16:00~17:00", "17:00~18:00",
]
# (프로젝트명 칸 있음?, 업무내용 텍스트)
_TMPL_ROWS = [
    (True,  "재실 이미지 전송 기능 추가"),
    (True,  "재실 이미지 전송 기능 추가"),
    (True,  "재실 이미지 전송 기능 추가"),
    (False, "점심 식사"),
    (True,  "앱 배포"),
    (True,  "LCS 연동 검토"),
    (True,  "LCS 연동 검토"),
    (True,  "LCS 연동 검토"),
    (True,  "UDP TEST"),
]


def _zip_replace(path, replacements):
    tmp = path + ".tmp"
    with zipfile.ZipFile(path, "r") as zin:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename.startswith("Contents/") and item.filename.endswith(".xml"):
                    text = data.decode("utf-8")
                    for old, new in replacements.items():
                        text = text.replace(old, new)
                    data = text.encode("utf-8")
                zout.writestr(item, data)
    os.replace(tmp, path)


def _zip_replace_seq(path, old, new_list):
    tmp = path + ".tmp"
    with zipfile.ZipFile(path, "r") as zin:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if "section" in item.filename and item.filename.endswith(".xml"):
                    text = data.decode("utf-8")
                    for new_val in new_list:
                        text = text.replace(old, new_val, 1)
                    data = text.encode("utf-8")
                zout.writestr(item, data)
    os.replace(tmp, path)


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
        self._last_log_raw = ""
        self.open_popups = []

        # 설정 로드
        config = self._load_config()

        # 커스텀 메뉴바
        menubar_frame = tk.Frame(root, bg="#f5f5f5")
        menubar_frame.pack(fill="x", side="top")

        self.autostart_var = tk.BooleanVar(value=self.get_autostart())
        self.auto_fill_var = tk.BooleanVar(value=config.get('auto_fill', True))

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
        settings_dropdown.add_checkbutton(
            label="이전 내용 자동 입력",
            variable=self.auto_fill_var,
            command=lambda: self._save_config('auto_fill', self.auto_fill_var.get())
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

        report_btn = tk.Button(
            menubar_frame, text="일일보고 생성",
            font=("Segoe UI", 9),
            bg="#f5f5f5", fg="#1a6bbf",
            activebackground="#e0e0e0", activeforeground="#1a6bbf",
            relief="flat", cursor="hand2", padx=8, pady=3, bd=0,
            command=self.generate_report
        )
        report_btn.pack(side="left")

        # 실시간 시계
        self.clock_label = tk.Label(
            root, text="",
            font=("Segoe UI", 20, "bold"),
            bg="#f5f5f5", fg="#222222"
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

        self.signature_label = tk.Label(
            root,
            text="@ 2026 Made by YKJ",
            font=("Segoe UI", 8),
            bg="#f5f5f5", fg="#cccccc"
        )
        self.signature_label.place(relx=1.0, rely=1.0, anchor='se', x=-5, y=-5)

        self.poll_log_file()

    # ── 설정 저장/로드 ────────────────────────────────────────────
    def _config_path(self):
        if hasattr(sys, '_MEIPASS'):
            d = os.path.dirname(sys.executable)
        else:
            d = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(d, 'config.json')

    def _load_config(self):
        try:
            with open(self._config_path(), 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_config(self, key, value):
        config = self._load_config()
        config[key] = value
        try:
            with open(self._config_path(), 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ── 자동실행 ────────────────────────────────────────────────
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

    # ── 로그 파일 ────────────────────────────────────────────────
    def get_today_filename(self):
        today = datetime.now().strftime("%Y-%m-%d")
        if hasattr(sys, '_MEIPASS'):
            exec_dir = os.path.dirname(sys.executable)
        else:
            exec_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(exec_dir, f"{today}.txt")

    def poll_log_file(self):
        filename = self.get_today_filename()
        if os.path.exists(filename):
            mtime = os.path.getmtime(filename)
            if mtime != self._log_file_mtime:
                self._log_file_mtime = mtime
                with open(filename, 'r', encoding='utf-8') as f:
                    lines = [l.rstrip() for l in f if l.strip()]
                if lines:
                    self._last_log_raw = lines[-1]
                    self.last_log_label.config(text=lines[-1].replace('\t', '  |  '))
                else:
                    self.last_log_label.config(text="-")
        elif self._log_file_mtime is not None:
            self._log_file_mtime = None
            self._last_log_raw = ""
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

    def copy_last_log(self):
        if not self._last_log_raw or self._last_log_raw == "-":
            return
        content = self._last_log_raw[20:].strip()  # 타임스탬프 제거
        if '\t' in content:
            content = content.split('\t', 1)[1]   # 업무내용만 복사
        self.root.clipboard_clear()
        self.root.clipboard_append(content)

    def write_log(self, text):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        filename = self.get_today_filename()
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(f"{now} {text}\n")
        self._log_file_mtime = os.path.getmtime(filename)
        self._last_log_raw = f"{now} {text}"
        self.last_log_label.config(text=f"{now} {text}".replace('\t', '  |  '))

    def _get_last_log_entry(self):
        """마지막 업무 로그의 (project, content)를 반환."""
        filename = self.get_today_filename()
        if not os.path.exists(filename):
            return '', ''
        with open(filename, 'r', encoding='utf-8') as f:
            lines = [l.rstrip() for l in f if l.strip()]
        for line in reversed(lines):
            parts = line.split(' ', 2)
            if len(parts) < 3:
                continue
            d = parts[2]
            if d == '출근' or '퇴근' in d:
                continue
            if '\t' in d:
                proj, desc = d.split('\t', 1)
                return proj, desc
            return '', d
        return '', ''

    # ── 출퇴근 ───────────────────────────────────────────────────
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

    # ── 정시 알람 팝업 ───────────────────────────────────────────
    def hourly_alarm(self):
        while self.alarm_running:
            now = datetime.now()
            next_hour = (now + timedelta(seconds=ALARM_INTERVAL_SECONDS)).replace(minute=0, second=0, microsecond=0)
            sleep_duration = (next_hour - now).total_seconds()
            time.sleep(sleep_duration)
            while datetime.now() < next_hour:
                time.sleep(0.01)
            if self.alarm_running:
                self.root.after(0, lambda t=next_hour: self.show_alarm_popup(t))

    def show_alarm_popup(self, current_time=None):
        if current_time is None:
            current_time = datetime.now().replace(minute=0, second=0, microsecond=0)

        if len(self.open_popups) >= 4:
            self.auto_end_day()
            return

        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)

        popup = tk.Toplevel()
        self.open_popups.append(popup)
        popup.title("정시 기록")
        popup.geometry("320x240")
        popup.resizable(False, False)
        popup.configure(bg="#f5f5f5")
        popup.attributes('-topmost', True)

        tk.Label(
            popup,
            text=current_time.strftime("%Y-%m-%d %H:%M"),
            font=("Segoe UI", 14, "bold"),
            bg="#f5f5f5", fg="#222222"
        ).pack(pady=(16, 8))

        # PROJECT명 입력
        tk.Label(popup, text="PROJECT명", font=("Segoe UI", 8),
                 bg="#f5f5f5", fg="#888888").pack(anchor="w", padx=20)
        proj_entry = tk.Entry(popup, width=36, font=("Segoe UI", 10), relief="solid", bd=1)
        proj_entry.pack(pady=(2, 6), padx=20)

        # 업무내용 입력
        tk.Label(popup, text="업무내용", font=("Segoe UI", 8),
                 bg="#f5f5f5", fg="#888888").pack(anchor="w", padx=20)
        desc_entry = tk.Entry(popup, width=36, font=("Segoe UI", 10), relief="solid", bd=1)
        desc_entry.pack(pady=(2, 6), padx=20)

        # 이전 내용 자동 입력
        if self.auto_fill_var.get():
            prev_proj, prev_desc = self._get_last_log_entry()
            if prev_proj:
                proj_entry.insert(0, prev_proj)
            if prev_desc:
                desc_entry.insert(0, prev_desc)
                desc_entry.select_range(0, 'end')
            desc_entry.focus_set()
        else:
            proj_entry.focus_set()

        def on_popup_close():
            if popup in self.open_popups:
                self.open_popups.remove(popup)
            popup.destroy()

        popup.protocol("WM_DELETE_WINDOW", on_popup_close)

        def save_entry(event=None):
            proj = proj_entry.get().strip()
            content = desc_entry.get().strip()
            if not content:
                messagebox.showwarning("입력 필요", "업무내용을 입력하세요.")
                return
            log_content = f"{proj}\t{content}" if proj else content
            filename = self.get_today_filename()
            log_text = f"{current_time.strftime('%Y-%m-%d %H:%M:%S')} {log_content}"
            with open(filename, 'a', encoding='utf-8') as f:
                f.write(f"{log_text}\n")
            self._log_file_mtime = os.path.getmtime(filename)
            self._last_log_raw = log_text
            self.last_log_label.config(text=log_text.replace('\t', '  |  '))
            if popup in self.open_popups:
                self.open_popups.remove(popup)
            popup.destroy()

        popup.bind("<Return>", save_entry)

        tk.Button(
            popup, text="기록", command=save_entry,
            font=("Segoe UI", 10, "bold"),
            bg="#4CAF50", fg="white",
            activebackground="#45a049", activeforeground="white",
            relief="flat", cursor="hand2", width=12
        ).pack(pady=8)

    # ── 일일보고 생성 ────────────────────────────────────────────
    def generate_report(self):
        log_file = self.get_today_filename()
        if not os.path.exists(log_file):
            messagebox.showinfo("알림", "오늘 기록된 파일이 없습니다.")
            return

        entries = []
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(' ', 2)
                if len(parts) < 3:
                    continue
                entries.append((parts[1], parts[2]))  # (HH:MM:SS, 내용)

        checkin_time = None
        checkout_time = None
        work_entries = []  # (HH:MM:SS, project, desc)
        for t, d in entries:
            if d == '출근':
                checkin_time = t
            elif '퇴근' in d:
                checkout_time = t
            else:
                if '\t' in d:
                    proj, desc = d.split('\t', 1)
                else:
                    proj, desc = '-', d
                work_entries.append((t, proj, desc))

        # 업무 행: 각 항목은 이전 항목 시각~현재 항목 시각 구간
        log_rows = []  # (time_range, project, desc)
        for i, (t, proj, desc) in enumerate(work_entries):
            start = checkin_time if i == 0 else work_entries[i - 1][0]
            log_rows.append((f"{(start or t)[:5]}~{t[:5]}", proj, desc))

        today = datetime.now()
        date_str = f"{today.year}년 {today.month:02d}월 {today.day:02d}일"

        work_hours = _TMPL_WORKHOURS
        if checkin_time and checkout_time:
            ci = datetime.strptime(checkin_time, "%H:%M:%S")
            co = datetime.strptime(checkout_time, "%H:%M:%S")
            h = int((co - ci).total_seconds() // 3600)
            work_hours = f" {h}시간"

        if hasattr(sys, '_MEIPASS'):
            exe_dir = os.path.dirname(sys.executable)
            tmpl_src = os.path.join(exe_dir, 'template.hwpx')
            if not os.path.exists(tmpl_src):
                tmpl_src = os.path.join(sys._MEIPASS, 'template.hwpx')
        else:
            tmpl_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'template.hwpx')

        if not os.path.exists(tmpl_src):
            messagebox.showerror("오류", "template.hwpx 파일을 찾을 수 없습니다.")
            return

        out_dir = os.path.dirname(log_file)
        date_suffix = today.strftime("%y_%m_%d")
        out_file = os.path.join(out_dir, f"일일업무보고_{date_suffix}.hwpx")

        try:
            shutil.copy(tmpl_src, out_file)

            # 1. 날짜·시각 직접 치환
            direct = {_TMPL_DATE: date_str}
            if checkin_time:
                direct[_TMPL_CHECKIN] = checkin_time
            if checkout_time:
                direct[_TMPL_CHECKOUT] = checkout_time
            direct[_TMPL_WORKHOURS] = work_hours
            for i, tmpl_time in enumerate(_TMPL_TIMES):
                direct[tmpl_time] = log_rows[i][0] if i < len(log_rows) else ""
            _zip_replace(out_file, direct)

            # 2. PROJECT명 순차 치환 (상업시설 × 8)
            proj_indices = [i for i, (has_proj, _) in enumerate(_TMPL_ROWS) if has_proj]
            proj_values = [log_rows[i][1] if i < len(log_rows) else "" for i in proj_indices]
            _zip_replace_seq(out_file, "상업시설", proj_values)

            # 3. 업무내용 순차 치환
            desc_groups = OrderedDict()
            for i, (_, desc) in enumerate(_TMPL_ROWS):
                desc_groups.setdefault(desc, []).append(i)
            for tmpl_desc, positions in desc_groups.items():
                values = [log_rows[pos][2] if pos < len(log_rows) else "" for pos in positions]
                if len(values) == 1:
                    _zip_replace(out_file, {tmpl_desc: values[0]})
                else:
                    _zip_replace_seq(out_file, tmpl_desc, values)

            os.startfile(out_file)
            messagebox.showinfo("완료", f"일일보고가 생성됐습니다.\n{os.path.basename(out_file)}")

        except Exception as e:
            messagebox.showerror("오류", f"보고서 생성 실패:\n{e}")


if __name__ == '__main__':
    root = tk.Tk()
    app = DailyReporter(root)
    root.mainloop()
