import tkinter as tk
from tkinter import messagebox
import sys
import os
import re
import csv
import io
import base64
import json
import zipfile
import winreg
from collections import OrderedDict
from datetime import datetime, timedelta
import threading
import time
import winsound

from _templates import (
    _TMPL_TIMES, _TMPL_REPORTER_PLACEHOLDER,
    _TMPL_DAILY_B64, _TMPL_WEEKLY_B64,
    _zip_replace_atomic, _fill_empty_runs, _parse_weekly_template_rows,
)

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
        self.auto_resume_var = tk.BooleanVar(value=config.get('auto_resume', True))

        settings_btn = tk.Button(
            menubar_frame, text="설정",
            font=("Segoe UI", 9),
            bg="#f5f5f5", fg="#555555",
            activebackground="#e0e0e0", activeforeground="#333333",
            relief="flat", cursor="hand2", padx=8, pady=3, bd=0,
            command=self._show_settings_window
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

        weekly_btn = tk.Button(
            menubar_frame, text="주간보고 생성",
            font=("Segoe UI", 9),
            bg="#f5f5f5", fg="#1a6bbf",
            activebackground="#e0e0e0", activeforeground="#1a6bbf",
            relief="flat", cursor="hand2", padx=8, pady=3, bd=0,
            command=self.show_weekly_date_picker
        )
        weekly_btn.pack(side="left")

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
        self.root.after(200, self._try_auto_resume)
        if not self._load_config().get('reporter_name', '').strip():
            self.root.after(300, self._show_settings_window)

    # ── 설정 저장/로드 ────────────────────────────────────────────
    def _show_settings_window(self):
        config = self._load_config()

        win = tk.Toplevel(self.root)
        win.title("설정")
        win.geometry("360x500")
        win.resizable(False, False)
        win.configure(bg="#f5f5f5")
        win.grab_set()

        # 스크롤 가능한 캔버스
        canvas = tk.Canvas(win, bg="#f5f5f5", highlightthickness=0)
        scrollbar = tk.Scrollbar(win, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        frame = tk.Frame(canvas, bg="#f5f5f5")
        frame_id = canvas.create_window((0, 0), window=frame, anchor="nw")

        def on_frame_configure(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_canvas_configure(event):
            canvas.itemconfig(frame_id, width=event.width)

        frame.bind("<Configure>", on_frame_configure)
        canvas.bind("<Configure>", on_canvas_configure)

        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<MouseWheel>", on_mousewheel)
        frame.bind("<MouseWheel>", on_mousewheel)

        # ── 헬퍼 ────────────────────────────────────────────────
        def section_label(text):
            tk.Label(frame, text=text, font=("Segoe UI", 8),
                     bg="#f5f5f5", fg="#aaaaaa").pack(anchor="w", padx=20, pady=(16, 2))

        def divider():
            tk.Frame(frame, height=1, bg="#e0e0e0").pack(fill="x", padx=20, pady=(8, 0))

        def checkbutton(text, var):
            cb = tk.Checkbutton(frame, text=text, variable=var,
                                font=("Segoe UI", 10),
                                bg="#f5f5f5", fg="#333333",
                                activebackground="#f5f5f5",
                                selectcolor="#f5f5f5")
            cb.pack(anchor="w", padx=16)
            cb.bind("<MouseWheel>", on_mousewheel)

        # ── 시스템 섹션 ──────────────────────────────────────────
        section_label("시스템")
        autostart_var = tk.BooleanVar(value=self.get_autostart())
        checkbutton("윈도우 시작 시 자동 실행", autostart_var)

        # ── 입력 섹션 ────────────────────────────────────────────
        divider()
        section_label("입력")
        auto_fill_var = tk.BooleanVar(value=config.get('auto_fill', True))
        checkbutton("이전 내용 자동 입력", auto_fill_var)
        auto_resume_var = tk.BooleanVar(value=config.get('auto_resume', True))
        checkbutton("시작 시 출근 상태 자동 복원", auto_resume_var)

        # ── 알림 섹션 ────────────────────────────────────────────
        divider()
        section_label("알림")
        tk.Label(frame, text="알림 울리는 분 (0~59)", font=("Segoe UI", 10),
                 bg="#f5f5f5", fg="#333333").pack(anchor="w", padx=20)
        tk.Label(frame, text="예: 50 → 매시 X시 50분에 알림", font=("Segoe UI", 8),
                 bg="#f5f5f5", fg="#aaaaaa").pack(anchor="w", padx=20)
        interval_var = tk.StringVar(value=str(config.get('alarm_minute', 0)))
        interval_entry = tk.Entry(frame, textvariable=interval_var,
                                  font=("Segoe UI", 10), width=10,
                                  justify="center", relief="solid", bd=1)
        interval_entry.pack(anchor="w", padx=20, pady=(2, 0))
        interval_entry.bind("<MouseWheel>", on_mousewheel)

        # ── 점심 시간 섹션 ──────────────────────────────────────
        divider()
        section_label("점심 시간")
        tk.Label(frame, text="해당 시간대 알림은 팝업 없이 '점심 시간'으로 자동 기록\n(비워두면 미사용)",
                 font=("Segoe UI", 8), bg="#f5f5f5", fg="#aaaaaa",
                 justify="left", wraplength=310).pack(anchor="w", padx=20)
        lunch_row = tk.Frame(frame, bg="#f5f5f5")
        lunch_row.pack(anchor="w", padx=20, pady=(4, 0))
        tk.Label(lunch_row, text="시작", font=("Segoe UI", 10),
                 bg="#f5f5f5", fg="#333333").pack(side="left")
        lunch_start_var = tk.StringVar(value=config.get('lunch_start', ''))
        lunch_start_entry = tk.Entry(lunch_row, textvariable=lunch_start_var,
                                     font=("Segoe UI", 10), width=7,
                                     justify="center", relief="solid", bd=1)
        lunch_start_entry.pack(side="left", padx=(4, 10))
        tk.Label(lunch_row, text="종료", font=("Segoe UI", 10),
                 bg="#f5f5f5", fg="#333333").pack(side="left")
        lunch_end_var = tk.StringVar(value=config.get('lunch_end', ''))
        lunch_end_entry = tk.Entry(lunch_row, textvariable=lunch_end_var,
                                   font=("Segoe UI", 10), width=7,
                                   justify="center", relief="solid", bd=1)
        lunch_end_entry.pack(side="left", padx=(4, 0))
        for w in (lunch_row, lunch_start_entry, lunch_end_entry):
            w.bind("<MouseWheel>", on_mousewheel)

        # ── 보고서 섹션 ──────────────────────────────────────────
        divider()
        section_label("보고서")
        tk.Label(frame, text="보고자 성명", font=("Segoe UI", 10),
                 bg="#f5f5f5", fg="#333333").pack(anchor="w", padx=20)
        name_var = tk.StringVar(value=config.get('reporter_name', ''))
        name_entry = tk.Entry(frame, textvariable=name_var,
                              font=("Segoe UI", 10), width=20,
                              relief="solid", bd=1)
        name_entry.pack(anchor="w", padx=20, pady=(2, 0))
        name_entry.bind("<MouseWheel>", on_mousewheel)

        # ── 저장 경로 섹션 ──────────────────────────────────────
        divider()
        section_label("저장 경로")
        tk.Label(frame, text="비워두면 exe 위치에 저장",
                 font=("Segoe UI", 8), bg="#f5f5f5", fg="#aaaaaa").pack(anchor="w", padx=20)

        def path_picker(label_text, config_key):
            tk.Label(frame, text=label_text, font=("Segoe UI", 10),
                     bg="#f5f5f5", fg="#333333").pack(anchor="w", padx=20, pady=(8, 0))
            var = tk.StringVar(value=config.get(config_key, '') or self._get_exe_dir())
            row = tk.Frame(frame, bg="#f5f5f5")
            row.pack(anchor="w", padx=20, pady=(2, 0), fill="x")
            entry = tk.Entry(row, textvariable=var, font=("Segoe UI", 9),
                             width=28, relief="solid", bd=1)
            entry.pack(side="left", padx=(0, 4))

            def browse(v=var):
                from tkinter import filedialog
                d = filedialog.askdirectory(parent=win, title=f"{label_text} 선택",
                                            initialdir=v.get())
                if d:
                    v.set(os.path.normpath(d))

            tk.Button(row, text="찾아보기", command=browse,
                      font=("Segoe UI", 9), bg="#e0e0e0", fg="#555555",
                      activebackground="#cccccc", activeforeground="#333333",
                      relief="flat", cursor="hand2", pady=3).pack(side="left")
            for w in (row, entry):
                w.bind("<MouseWheel>", on_mousewheel)
            return var

        log_dir_var = path_picker("로그 파일 저장 경로", "log_dir")
        daily_dir_var = path_picker("일일업무보고 저장 경로", "daily_report_dir")
        weekly_dir_var = path_picker("주간업무보고 저장 경로", "weekly_report_dir")

        # ── 저장 버튼 ────────────────────────────────────────────
        divider()

        def on_save():
            try:
                alarm_minute = int(interval_var.get().strip())
                if not (0 <= alarm_minute <= 59):
                    raise ValueError
            except ValueError:
                messagebox.showerror("오류", "알림 울리는 분은 0~59 사이의 정수를 입력하세요.", parent=win)
                return

            if autostart_var.get() != self.autostart_var.get():
                self.autostart_var.set(autostart_var.get())
                self.toggle_autostart()

            self.auto_fill_var.set(auto_fill_var.get())
            self.auto_resume_var.set(auto_resume_var.get())

            cfg = self._load_config()
            lunch_start = lunch_start_var.get().strip()
            lunch_end = lunch_end_var.get().strip()
            if lunch_start or lunch_end:
                try:
                    if not lunch_start or not lunch_end:
                        raise ValueError
                    s = datetime.strptime(lunch_start, "%H:%M")
                    e = datetime.strptime(lunch_end, "%H:%M")
                    if s >= e:
                        raise ValueError
                except ValueError:
                    messagebox.showerror("오류",
                        "점심 시간 형식이 올바르지 않습니다.\n"
                        "HH:MM 형식으로 입력하고 시작 < 종료여야 합니다.\n"
                        "예: 12:00 ~ 13:00", parent=win)
                    return

            exe_dir = self._get_exe_dir()
            dir_fields = [
                ('log_dir', log_dir_var, "로그 파일 저장 경로"),
                ('daily_report_dir', daily_dir_var, "일일업무보고 저장 경로"),
                ('weekly_report_dir', weekly_dir_var, "주간업무보고 저장 경로"),
            ]
            for key, var, label in dir_fields:
                d = var.get().strip()
                if d and d != exe_dir and not os.path.isdir(d):
                    messagebox.showerror("오류",
                        f"[{label}] 경로가 존재하지 않습니다:\n{d}", parent=win)
                    return

            cfg['auto_fill'] = auto_fill_var.get()
            cfg['auto_resume'] = auto_resume_var.get()
            cfg['alarm_minute'] = alarm_minute
            cfg['lunch_start'] = lunch_start
            cfg['lunch_end'] = lunch_end
            cfg['reporter_name'] = name_var.get().strip()
            for key, var, _ in dir_fields:
                d = var.get().strip()
                cfg[key] = '' if (not d or d == exe_dir) else d
            try:
                with open(self._config_path(), 'w', encoding='utf-8') as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
            except Exception as e:
                messagebox.showerror("오류", f"설정 저장 실패:\n{e}", parent=win)
                return

            win.destroy()

        btn_row = tk.Frame(frame, bg="#f5f5f5")
        btn_row.pack(pady=(12, 20))
        btn_row.bind("<MouseWheel>", on_mousewheel)

        tk.Button(btn_row, text="저장", command=on_save,
                  font=("Segoe UI", 10, "bold"),
                  bg="#1a6bbf", fg="white",
                  activebackground="#155a99", activeforeground="white",
                  relief="flat", cursor="hand2",
                  width=10, pady=5).pack(side="left", padx=(0, 6))

        tk.Button(btn_row, text="취소", command=win.destroy,
                  font=("Segoe UI", 10),
                  bg="#e0e0e0", fg="#555555",
                  activebackground="#cccccc", activeforeground="#333333",
                  relief="flat", cursor="hand2",
                  width=10, pady=5).pack(side="left")

    def _config_path(self):
        return os.path.join(self._get_exe_dir(), 'config.json')

    def _load_config(self):
        try:
            with open(self._config_path(), 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def _is_lunch_time(self, dt):
        config = self._load_config()
        lunch_start = config.get('lunch_start', '').strip()
        lunch_end = config.get('lunch_end', '').strip()
        if not lunch_start or not lunch_end:
            return False
        try:
            s_hour, s_min = map(int, lunch_start.split(':'))
            e_hour, e_min = map(int, lunch_end.split(':'))
            start = dt.replace(hour=s_hour, minute=s_min, second=0, microsecond=0)
            end = dt.replace(hour=e_hour, minute=e_min, second=0, microsecond=0)
            return start <= dt < end
        except (ValueError, AttributeError):
            return False

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
    def _get_exe_dir(self):
        if hasattr(sys, '_MEIPASS'):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def _resolve_dir(self, config_key):
        d = self._load_config().get(config_key, '').strip()
        if d and os.path.isdir(d):
            return d
        return self._get_exe_dir()

    def _get_log_dir(self):
        return self._resolve_dir('log_dir')

    def _get_daily_report_dir(self):
        return self._resolve_dir('daily_report_dir')

    def _get_weekly_report_dir(self):
        return self._resolve_dir('weekly_report_dir')

    def get_today_filename(self):
        today = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self._get_log_dir(), f"{today}.csv")

    def _parse_csv_line(self, line):
        """CSV 한 줄을 (date, time, project, desc) 로 파싱. 실패 시 None."""
        try:
            row = next(csv.reader(io.StringIO(line)))
            if len(row) >= 4:
                return tuple(row[:4])
            if len(row) == 3:
                return (row[0], row[1], row[2], '')
        except Exception:
            pass
        return None

    def _round_alarm_log_time(self, alarm_minute, t):
        if alarm_minute == 0 or alarm_minute == 30:
            return t
        elif 1 <= alarm_minute <= 29:
            return t.replace(minute=0, second=0, microsecond=0)
        else:
            return t.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

    def _write_log_row(self, proj, desc, dt=None):
        """CSV 행 한 줄을 파일에 append하고 raw 라인 문자열을 반환."""
        now = dt if dt is not None else datetime.now()
        filename = self.get_today_filename()
        buf = io.StringIO()
        csv.writer(buf).writerow([now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), proj, desc])
        raw = buf.getvalue().rstrip('\r\n')
        with open(filename, 'a', encoding='utf-8-sig', newline='') as f:
            f.write(raw + '\n')
        self._log_file_mtime = os.path.getmtime(filename)
        return raw

    def poll_log_file(self):
        filename = self.get_today_filename()
        if os.path.exists(filename):
            mtime = os.path.getmtime(filename)
            if mtime != self._log_file_mtime:
                self._log_file_mtime = mtime
                with open(filename, 'r', encoding='utf-8-sig') as f:
                    lines = [l.rstrip() for l in f if l.strip()]
                if lines:
                    self._last_log_raw = lines[-1]
                    self.last_log_label.config(text=self._format_log_display(lines[-1]))
                else:
                    self.last_log_label.config(text="-")
        elif self._log_file_mtime is not None:
            self._log_file_mtime = None
            self._last_log_raw = ""
            self.last_log_label.config(text="-")
        self.root.after(5000, self.poll_log_file)

    def _format_log_display(self, raw):
        """CSV raw 라인을 UI 표시용 문자열로 변환."""
        parsed = self._parse_csv_line(raw)
        if not parsed:
            return raw
        date, time_, proj, desc = parsed
        base = f"{date} {time_}"
        if proj and desc:
            return f"{base} {proj}  |  {desc}"
        if proj:
            return f"{base} {proj}"
        return base

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
        parsed = self._parse_csv_line(self._last_log_raw)
        content = parsed[3] if parsed and parsed[3] else (parsed[2] if parsed else self._last_log_raw)
        self.root.clipboard_clear()
        self.root.clipboard_append(content)

    def write_log(self, text, dt=None):
        raw = self._write_log_row(text, "", dt)
        self._last_log_raw = raw
        self.last_log_label.config(text=self._format_log_display(raw))

    def _get_last_log_entry(self):
        """마지막 업무 로그의 (project, content)를 반환."""
        filename = self.get_today_filename()
        if not os.path.exists(filename):
            return '', ''
        with open(filename, 'r', encoding='utf-8-sig') as f:
            lines = [l.rstrip() for l in f if l.strip()]
        for line in reversed(lines):
            parsed = self._parse_csv_line(line)
            if not parsed:
                continue
            _, _, proj, desc = parsed
            if proj == '출근' or '퇴근' in proj or proj == '점심 시간':
                continue
            return proj, desc
        return '', ''

    # ── 출퇴근 ───────────────────────────────────────────────────
    def _resume_checkin(self):
        """출근 UI/상태 전환 (로그 쓰기 없음). start_day와 _try_auto_resume에서 공유."""
        self.alarm_running = True
        self.start_button.config(state="disabled", bg="#cccccc", fg="#aaaaaa", cursor="arrow")
        self.end_button.config(state="normal", bg="#f44336", fg="white",
                               activebackground="#e53935", activeforeground="white", cursor="hand2")
        self.status_label.config(text="열일중!", fg="#f44336")
        threading.Thread(target=self.hourly_alarm, daemon=True).start()

    def start_day(self):
        if not self.alarm_running:
            self.write_log("출근")
            self._resume_checkin()

    def _try_auto_resume(self):
        """오늘 로그에 출근 기록이 있고 퇴근이 없으면 자동으로 출근 상태로 복원."""
        if self.alarm_running or not self.auto_resume_var.get():
            return
        filename = self.get_today_filename()
        if not os.path.exists(filename):
            return
        has_checkin = False
        has_checkout = False
        with open(filename, 'r', encoding='utf-8-sig', newline='') as f:
            for row in csv.reader(f):
                if len(row) < 3:
                    continue
                proj = row[2]
                if proj == '출근':
                    has_checkin = True
                elif '퇴근' in proj:
                    has_checkout = True
        if has_checkin and not has_checkout:
            self._resume_checkin()

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
            alarm_minute = self._load_config().get('alarm_minute', 0)
            now = datetime.now()
            next_mark = now.replace(minute=alarm_minute, second=0, microsecond=0)
            if next_mark <= now:
                next_mark += timedelta(hours=1)

            # 10초마다 설정 변경 여부를 확인하며 대기
            while self.alarm_running:
                now = datetime.now()
                if now >= next_mark:
                    break
                new_minute = self._load_config().get('alarm_minute', 0)
                if new_minute != alarm_minute:
                    alarm_minute = new_minute
                    candidate = now.replace(minute=alarm_minute, second=0, microsecond=0)
                    if candidate <= now:
                        candidate += timedelta(hours=1)
                    next_mark = candidate
                    continue
                remaining = (next_mark - now).total_seconds()
                time.sleep(min(10, remaining))

            if self.alarm_running:
                log_time = self._round_alarm_log_time(alarm_minute, next_mark)
                if self._is_lunch_time(next_mark):
                    self.root.after(0, lambda t=log_time: self.write_log("점심 시간", t))
                else:
                    self.root.after(0, lambda t=next_mark: self.show_alarm_popup(t))

    def show_alarm_popup(self, current_time=None):
        if current_time is None:
            current_time = datetime.now().replace(minute=0, second=0, microsecond=0)

        if len(self.open_popups) >= 4:
            self.auto_end_day()
            return

        # alarm_minute 기준으로 로그에 기록할 정각 시간 계산
        alarm_minute = self._load_config().get('alarm_minute', 0)
        log_time = self._round_alarm_log_time(alarm_minute, current_time)

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
            text=log_time.strftime("%Y-%m-%d %H:%M"),
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
            buf = io.StringIO()
            csv.writer(buf).writerow([
                log_time.strftime('%Y-%m-%d'),
                log_time.strftime('%H:%M:%S'),
                proj, content
            ])
            raw = buf.getvalue().rstrip('\r\n')
            filename = self.get_today_filename()
            with open(filename, 'a', encoding='utf-8-sig', newline='') as f:
                f.write(raw + '\n')
            self._log_file_mtime = os.path.getmtime(filename)
            self._last_log_raw = raw
            display = f"{proj}  |  {content}" if proj else content
            self.last_log_label.config(text=display)
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

        checkin_time = None
        checkout_time = None
        log_date = None
        work_entries = []  # (HH:MM:SS, project, desc)
        with open(log_file, 'r', encoding='utf-8-sig', newline='') as f:
            for row in csv.reader(f):
                if len(row) < 3:
                    continue
                if log_date is None and row[0]:
                    log_date = row[0]  # YYYY-MM-DD
                t, proj = row[1], row[2]
                desc = row[3] if len(row) >= 4 else ''
                if proj == '출근':
                    checkin_time = t
                elif '퇴근' in proj:
                    checkout_time = t
                else:
                    work_entries.append((t, proj, desc))

        # 로그 순서대로 템플릿 행에 순차 배정
        log_rows = []  # (time_range, proj, desc)
        for i, (t, proj, desc) in enumerate(work_entries[:len(_TMPL_TIMES)]):
            start = "09:00:00" if i == 0 else work_entries[i - 1][0]
            log_rows.append((f"{(start or t)[:5]}~{t[:5]}", proj, desc))

        # 날짜는 로그 파일 기준
        if log_date:
            d = datetime.strptime(log_date, "%Y-%m-%d")
        else:
            d = datetime.now()
        date_str = f"{d.year}년 {d.month:02d}월 {d.day:02d}일"

        work_hours_str = None
        if checkin_time and checkout_time:
            ci = datetime.strptime(checkin_time, "%H:%M:%S")
            co = datetime.strptime(checkout_time, "%H:%M:%S")
            h = int((co - ci).total_seconds() // 3600)
            work_hours_str = f" {h}시간"

        out_dir = self._get_daily_report_dir()
        date_suffix = d.strftime("%y%m%d")
        out_file = os.path.join(out_dir, f"유타렉스_일일업무보고_{date_suffix}.hwpx")

        try:
            # 템플릿 XML을 메모리에서 수정 후 한 번에 기록
            tmpl_bytes = base64.b64decode(_TMPL_DAILY_B64)
            with zipfile.ZipFile(io.BytesIO(tmpl_bytes), 'r') as zin:
                entries = [(item, zin.read(item.filename)) for item in zin.infolist()]

            section_idx = next(
                i for i, (item, _) in enumerate(entries)
                if 'section' in item.filename and item.filename.endswith('.xml')
            )
            xml = entries[section_idx][1].decode('utf-8')

            # 1. 날짜·시각 동적 치환 (템플릿의 패턴을 찾아 교체)
            xml = re.sub(r'\d{4}년 \d{2}월 \d{2}일', date_str, xml)

            # HH:MM:SS 패턴 순서대로 첫 번째=출근, 두 번째=퇴근으로 단일 패스 치환
            _time_count = [0]
            def _replace_hms(m):
                _time_count[0] += 1
                if _time_count[0] == 1:
                    return checkin_time if checkin_time else m.group()
                if _time_count[0] == 2:
                    return checkout_time if checkout_time else m.group()
                return m.group()
            xml = re.sub(r'\d{2}:\d{2}:\d{2}', _replace_hms, xml)

            if work_hours_str:
                xml = re.sub(r' *\d+시간', work_hours_str, xml, count=1)

            reporter_name = self._load_config().get('reporter_name', '홍길동') or '홍길동'
            xml = xml.replace(_TMPL_REPORTER_PLACEHOLDER, reporter_name)

            # 2. 시간 슬롯별: 시간 텍스트 교체 + 프로젝트·업무내용 삽입
            prev_end = 0
            for i, slot in enumerate(_TMPL_TIMES):
                slot_pos = xml.find(slot, prev_end)  # 이미 처리된 구간 재탐색 방지
                if slot_pos == -1:
                    continue
                next_pos = len(xml)
                for next_slot in _TMPL_TIMES[i + 1:]:
                    p = xml.find(next_slot, slot_pos)
                    if p != -1:
                        next_pos = p
                        break
                row_frag = xml[slot_pos:next_pos]
                if i < len(log_rows):
                    time_range, proj, desc = log_rows[i]
                    row_frag = row_frag.replace(slot, time_range, 1)
                    row_frag = _fill_empty_runs(row_frag, [proj, desc])
                else:
                    row_frag = row_frag.replace(slot, '', 1)
                xml = xml[:slot_pos] + row_frag + xml[next_pos:]
                prev_end = slot_pos + len(row_frag)

            # 수정된 XML을 출력 파일에 단일 패스로 기록
            with zipfile.ZipFile(out_file, 'w', zipfile.ZIP_DEFLATED) as zout:
                for idx, (item, data) in enumerate(entries):
                    zout.writestr(item, xml.encode('utf-8') if idx == section_idx else data)

            os.startfile(out_file)
            messagebox.showinfo("완료", f"일일보고가 생성됐습니다.\n{os.path.basename(out_file)}")

        except Exception as e:
            messagebox.showerror("오류", f"보고서 생성 실패:\n{e}")

    def show_weekly_date_picker(self):
        today = datetime.now().date()
        # 저번 주 월요일: 이번 주 월요일에서 7일 전
        last_monday = today - timedelta(days=today.weekday() + 7)
        last_friday = last_monday + timedelta(days=4)

        popup = tk.Toplevel(self.root)
        popup.title("주간보고 기간 선택")
        popup.geometry("300x160")
        popup.resizable(False, False)
        popup.configure(bg="#f5f5f5")
        popup.grab_set()

        tk.Label(popup, text="시작일 (YYYY-MM-DD)", bg="#f5f5f5", font=("Segoe UI", 9)).pack(pady=(16, 2))
        start_var = tk.StringVar(value=last_monday.strftime("%Y-%m-%d"))
        start_entry = tk.Entry(popup, textvariable=start_var, font=("Segoe UI", 10), width=18, justify="center")
        start_entry.pack()

        tk.Label(popup, text="종료일 (YYYY-MM-DD)", bg="#f5f5f5", font=("Segoe UI", 9)).pack(pady=(8, 2))
        end_var = tk.StringVar(value=last_friday.strftime("%Y-%m-%d"))
        end_entry = tk.Entry(popup, textvariable=end_var, font=("Segoe UI", 10), width=18, justify="center")
        end_entry.pack()

        def on_generate():
            try:
                start = datetime.strptime(start_var.get().strip(), "%Y-%m-%d").date()
                end = datetime.strptime(end_var.get().strip(), "%Y-%m-%d").date()
            except ValueError:
                messagebox.showerror("오류", "날짜 형식이 올바르지 않습니다.\nYYYY-MM-DD 형식으로 입력하세요.", parent=popup)
                return
            if start > end:
                messagebox.showerror("오류", "시작일이 종료일보다 늦습니다.", parent=popup)
                return
            popup.destroy()
            self.generate_weekly_report(start, end)

        tk.Button(
            popup, text="생성하기",
            font=("Segoe UI", 10, "bold"),
            bg="#1a6bbf", fg="white",
            activebackground="#155a99", activeforeground="white",
            relief="flat", cursor="hand2", padx=12, pady=4,
            command=on_generate
        ).pack(pady=(12, 0))
        popup.bind("<Return>", lambda e: on_generate())
        start_entry.focus_set()

    def generate_weekly_report(self, start_date, end_date):
        # 날짜 범위의 로그 수집
        proj_descs = OrderedDict()  # {project: [desc, ...]} 중복 없이
        log_dir = os.path.dirname(self.get_today_filename())
        cur = start_date
        while cur <= end_date:
            log_file = os.path.join(log_dir, cur.strftime("%Y-%m-%d") + ".csv")
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8-sig', newline='') as f:
                    for row in csv.reader(f):
                        if len(row) < 3:
                            continue
                        proj_raw = row[2]
                        desc = row[3].strip() if len(row) >= 4 else ''
                        if proj_raw == '출근' or '퇴근' in proj_raw:
                            continue
                        # "피플카운터, 집합수요" 형태의 복합 프로젝트 분리
                        projects = [p.strip() for p in proj_raw.split(',') if p.strip()] or ['']
                        for proj in projects:
                            if proj not in proj_descs:
                                proj_descs[proj] = []
                            if desc and desc not in proj_descs[proj]:
                                proj_descs[proj].append(desc)
            cur += timedelta(days=1)

        if not proj_descs:
            messagebox.showinfo("알림", "선택한 기간에 기록된 업무가 없습니다.")
            return

        # 최대 6행, 각 행: (project, aggregated_desc)
        rows = []
        for proj, descs in list(proj_descs.items())[:6]:
            rows.append((proj, ', '.join(descs)))

        friday_str = end_date.strftime("%m.%d")
        out_dir = self._get_weekly_report_dir()
        date_suffix = datetime.now().strftime("%y%m%d")
        out_file = os.path.join(out_dir, f"유타렉스_주간업무보고_{date_suffix}.hwpx")

        try:
            tmpl_bytes = base64.b64decode(_TMPL_WEEKLY_B64)
            with open(out_file, 'wb') as f:
                f.write(tmpl_bytes)

            date_str, tmpl_rows = _parse_weekly_template_rows(tmpl_bytes)

            reporter_name = self._load_config().get('reporter_name', '홍길동') or '홍길동'
            direct_map = {_TMPL_REPORTER_PLACEHOLDER: reporter_name}
            if date_str:
                direct_map[date_str] = friday_str

            # proj/desc 텍스트별 치환값 목록 수집 (중복 텍스트 → seq_map)
            proj_vals = {}  # text -> [replacement, ...]
            desc_vals = {}

            for i, (proj_texts, desc_texts) in enumerate(tmpl_rows):
                log_proj = rows[i][0] if i < len(rows) else ''
                log_desc = rows[i][1] if i < len(rows) else ''
                for j, t in enumerate(proj_texts):
                    proj_vals.setdefault(t, []).append(log_proj if j == 0 else '')
                for j, t in enumerate(desc_texts):
                    desc_vals.setdefault(t, []).append(log_desc if j == 0 else '')

            seq_map = {}
            for vals_dict in (proj_vals, desc_vals):
                for t, vals in vals_dict.items():
                    if len(vals) == 1 or len(set(vals)) == 1:
                        direct_map[t] = vals[0]
                    else:
                        seq_map[t] = vals

            _zip_replace_atomic(out_file, direct_map, seq_map)

            os.startfile(out_file)
            messagebox.showinfo("완료", f"주간보고가 생성됐습니다.\n{os.path.basename(out_file)}")

        except Exception as e:
            messagebox.showerror("오류", f"주간보고 생성 실패:\n{e}")


if __name__ == '__main__':
    root = tk.Tk()
    app = DailyReporter(root)
    root.mainloop()
