import subprocess
import sys
from hwpx import HwpxDocument

SKILL_SCRIPTS = "C:/Users/kjyan/work/02_SOURCE/DailyReporter/fix_namespaces.py"
OUTPUT = "C:/Users/kjyan/work/02_SOURCE/DailyReporter/dist/2026-04-21-업무일지.hwpx"

work_log = [
    ("09:06", "출근"),
    ("10:00", "홈페이지 이미지 수정, 기능개선"),
    ("11:00", "홈페이지 기능개선"),
    ("12:00", "웹사이트 기능개선"),
    ("13:00", "점심"),
    ("14:00", "홈페이지 테스트"),
    ("15:00", "Matter SDK TEST"),
    ("16:00", "Matter Hub Test"),
]

doc = HwpxDocument.new()

doc.add_paragraph("2026년 4월 21일 업무일지", style="제목")

table = doc.add_table(rows=len(work_log) + 1, cols=2)
table.set_cell_text(0, 0, "시간")
table.set_cell_text(0, 1, "업무 내용")

for i, (time, task) in enumerate(work_log, start=1):
    table.set_cell_text(i, 0, time)
    table.set_cell_text(i, 1, task)

doc.save(OUTPUT)
print(f"저장 완료: {OUTPUT}")

subprocess.run([sys.executable, SKILL_SCRIPTS, OUTPUT], check=True)
print("네임스페이스 후처리 완료")
