import io
import os
from datetime import datetime
import pandas as pd
from flask import Flask, flash, redirect, render_template, request, send_file, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from fpdf import FPDF
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from models import db, User, Student, Room, Exam, SeatingAllocation

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-demo-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "exam_seating.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def role_required(*roles):
    from functools import wraps
    def decorate(fn):
        @wraps(fn)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                flash("You do not have permission to open that page.", "danger")
                return redirect(url_for("home"))
            return fn(*args, **kwargs)
        return wrapped
    return decorate

def seed_data():
    if not User.query.filter_by(username="admin").first():
        db.session.add_all([
            User(username="admin", password_hash=generate_password_hash("admin123"), role="admin"),
            User(username="student", password_hash=generate_password_hash("student123"), role="student", roll_no="CSE001"),
            User(username="faculty", password_hash=generate_password_hash("faculty123"), role="faculty"),
        ])
    if Student.query.count() == 0:
        db.session.add_all([
            Student(roll_no="CSE001", name="Aarav Sharma", branch="CSE", semester="5"),
            Student(roll_no="ECE001", name="Diya Verma", branch="ECE", semester="5"),
            Student(roll_no="ME001", name="Kabir Singh", branch="ME", semester="5"),
            Student(roll_no="CSE002", name="Anaya Gupta", branch="CSE", semester="5"),
            Student(roll_no="ECE002", name="Vivaan Patel", branch="ECE", semester="5"),
            Student(roll_no="ME002", name="Sara Khan", branch="ME", semester="5"),
            Student(roll_no="CSE003", name="Arjun Das", branch="CSE", semester="5"),
            Student(roll_no="ECE003", name="Isha Roy", branch="ECE", semester="5"),
        ])
    if Room.query.count() == 0:
        db.session.add_all([
            Room(room_no="R101", capacity=12, rows=3, cols=2, benches=6),
            Room(room_no="R102", capacity=8, rows=2, cols=2, benches=4),
        ])
    db.session.commit()

with app.app_context():
    db.create_all()
    seed_data()

def read_upload(file):
    filename = secure_filename(file.filename or "")
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".csv":
        return pd.read_csv(file)
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(file)
    raise ValueError("Choose a .csv or .xlsx file.")

def interleave_students(students):
    groups = {}
    for student in students:
        groups.setdefault(student.branch.strip().upper(), []).append(student)
    result = []
    branches = sorted(groups)
    while any(groups.values()):
        for branch in branches:
            if groups[branch]:
                result.append(groups[branch].pop(0))
    return result

def overlaps(exam1, exam2):
    return (exam1.exam_date == exam2.exam_date and
            exam1.start_time < exam2.end_time and exam2.start_time < exam1.end_time)

def allocate(exam):
    SeatingAllocation.query.filter_by(exam_id=exam.id).delete()
    db.session.flush()
    query = Student.query
    if exam.semester.strip().lower() != "all":
        query = query.filter_by(semester=exam.semester.strip())
    students = interleave_students(query.order_by(Student.roll_no).all())
    if not students:
        raise ValueError("No students found for this semester.")
    rooms = Room.query.order_by(Room.room_no).all()
    if not rooms:
        raise ValueError("Add at least one room first.")
    total_capacity = 0
    positions = []
    for room in rooms:
        if min(room.capacity, room.rows, room.cols, room.benches) <= 0:
            raise ValueError(f"Room {room.room_no} has invalid values.")
        if room.benches > room.rows * room.cols:
            raise ValueError(f"{room.room_no}: benches cannot exceed rows × columns.")
        if room.capacity > room.benches * 2:
            raise ValueError(f"{room.room_no}: capacity cannot exceed 2 × benches.")
        total_capacity += room.capacity
        seats_left = room.capacity
        for bench in range(1, room.benches + 1):
            row = (bench - 1) // room.cols + 1
            col = (bench - 1) % room.cols + 1
            for seat in (1, 2):
                if seats_left <= 0:
                    break
                positions.append((room, bench, row, col, seat))
                seats_left -= 1
            if seats_left <= 0:
                break
    if len(students) > total_capacity:
        raise ValueError(f"Not enough seats: {len(students)} students, capacity is {total_capacity}.")
    for allocation in SeatingAllocation.query.join(Exam).all():
        if allocation.exam_id != exam.id and overlaps(exam, allocation.exam):
            if allocation.student.roll_no in {s.roll_no for s in students}:
                raise ValueError(f"Schedule conflict: {allocation.student.roll_no} has another exam at this time.")
    # Prefer different branches on each two-seat bench; swap forward if needed.
    for i in range(0, len(students) - 1, 2):
        if students[i].branch.casefold() == students[i + 1].branch.casefold():
            swap = next((j for j in range(i + 2, len(students))
                         if students[j].branch.casefold() != students[i].branch.casefold()), None)
            if swap is not None:
                students[i + 1], students[swap] = students[swap], students[i + 1]
    for student, pos in zip(students, positions):
        room, bench, row, col, seat = pos
        db.session.add(SeatingAllocation(exam_id=exam.id, student_id=student.id, room_id=room.id,
            bench_no=bench, row_no=row, col_no=col, seat_on_bench=seat))
    db.session.commit()
    return len(students)

@app.route("/")
def home():
    if not current_user.is_authenticated:
        return redirect(url_for("login"))
    if current_user.role == "admin":
        return redirect(url_for("admin_dashboard"))
    if current_user.role == "student":
        return redirect(url_for("student_search"))
    return redirect(url_for("reports"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    if request.method == "POST":
        user = User.query.filter_by(username=request.form.get("username", "").strip()).first()
        if user and check_password_hash(user.password_hash, request.form.get("password", "")):
            login_user(user)
            return redirect(url_for("home"))
        flash("Incorrect username or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/admin")
@role_required("admin")
def admin_dashboard():
    return render_template("admin_dashboard.html",
        student_count=Student.query.count(), room_count=Room.query.count(),
        exam_count=Exam.query.count(), students=Student.query.order_by(Student.roll_no).all(),
        rooms=Room.query.order_by(Room.room_no).all(),
        exams=Exam.query.order_by(Exam.exam_date.desc()).all())

@app.route("/upload", methods=["GET", "POST"])
@role_required("admin")
def upload():
    if request.method == "POST":
        file = request.files.get("file")
        kind = request.form.get("upload_type")
        if not file or not file.filename:
            flash("Choose a file first.", "danger")
            return redirect(url_for("upload"))
        try:
            data = read_upload(file)
            data.columns = [str(c).strip().lower().replace(" ", "_") for c in data.columns]
            if kind == "students":
                needed = {"roll_no", "name", "branch", "semester"}
                if not needed.issubset(data.columns):
                    raise ValueError("Student columns required: roll_no, name, branch, semester.")
                count = 0
                for _, r in data.iterrows():
                    roll = str(r["roll_no"]).strip()
                    if not roll or roll.lower() == "nan":
                        continue
                    s = Student.query.filter_by(roll_no=roll).first()
                    if not s:
                        s = Student(roll_no=roll, name=str(r["name"]).strip(),
                                    branch=str(r["branch"]).strip(), semester=str(r["semester"]).strip())
                        db.session.add(s)
                    else:
                        s.name, s.branch, s.semester = str(r["name"]).strip(), str(r["branch"]).strip(), str(r["semester"]).strip()
                    count += 1
            elif kind == "rooms":
                needed = {"room_no", "capacity", "rows", "cols", "benches"}
                if not needed.issubset(data.columns):
                    raise ValueError("Room columns required: room_no, capacity, rows, cols, benches.")
                count = 0
                for _, r in data.iterrows():
                    room_no = str(r["room_no"]).strip()
                    vals = [int(r[k]) for k in ("capacity", "rows", "cols", "benches")]
                    capacity, rows, cols, benches = vals
                    if not room_no or min(vals) <= 0 or benches > rows * cols or capacity > benches * 2:
                        raise ValueError(f"Invalid room values for {room_no}.")
                    room = Room.query.filter_by(room_no=room_no).first()
                    if not room:
                        room = Room(room_no=room_no)
                        db.session.add(room)
                    room.capacity, room.rows, room.cols, room.benches = vals
                    count += 1
            else:
                raise ValueError("Select Students or Rooms upload.")
            db.session.commit()
            flash(f"Imported/updated {count} records.", "success")
        except Exception as error:
            db.session.rollback()
            flash(f"Upload failed: {error}", "danger")
        return redirect(url_for("upload"))
    return render_template("upload.html")

@app.route("/students/add", methods=["POST"])
@role_required("admin")
def add_student():
    vals = [request.form.get(k, "").strip() for k in ("roll_no", "name", "branch", "semester")]
    if not all(vals):
        flash("Fill all student fields.", "danger")
    elif Student.query.filter_by(roll_no=vals[0]).first():
        flash("Roll number already exists.", "danger")
    else:
        db.session.add(Student(roll_no=vals[0], name=vals[1], branch=vals[2], semester=vals[3]))
        db.session.commit()
        flash("Student added.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/rooms/add", methods=["POST"])
@role_required("admin")
def add_room():
    try:
        room_no = request.form.get("room_no", "").strip()
        cap, rows, cols, benches = [int(request.form.get(k, "0")) for k in ("capacity", "rows", "cols", "benches")]
        if not room_no or min(cap, rows, cols, benches) <= 0 or benches > rows * cols or cap > benches * 2:
            raise ValueError("Check room number, capacity and layout values.")
        if Room.query.filter_by(room_no=room_no).first():
            raise ValueError("Room number already exists.")
        db.session.add(Room(room_no=room_no, capacity=cap, rows=rows, cols=cols, benches=benches))
        db.session.commit()
        flash("Room added.", "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("admin_dashboard"))

@app.route("/exams/create", methods=["POST"])
@role_required("admin")
def create_exam():
    try:
        name, subject = request.form.get("name", "").strip(), request.form.get("subject", "").strip()
        day, start, end = request.form.get("exam_date", ""), request.form.get("start_time", ""), request.form.get("end_time", "")
        semester = request.form.get("semester", "All").strip() or "All"
        datetime.strptime(day, "%Y-%m-%d")
        if datetime.strptime(end, "%H:%M") <= datetime.strptime(start, "%H:%M"):
            raise ValueError("End time must be later than start time.")
        if not name or not subject:
            raise ValueError("Exam name and subject are required.")
        db.session.add(Exam(name=name, subject=subject, exam_date=day, start_time=start, end_time=end, semester=semester))
        db.session.commit()
        flash("Exam created.", "success")
    except ValueError as e:
        flash(f"Invalid exam details: {e}", "danger")
    return redirect(url_for("admin_dashboard"))

@app.route("/exams/<int:exam_id>/allocate", methods=["POST"])
@role_required("admin")
def generate_seating(exam_id):
    exam = db.session.get(Exam, exam_id)
    if not exam:
        flash("Exam not found.", "danger")
        return redirect(url_for("admin_dashboard"))
    try:
        count = allocate(exam)
        flash(f"Allocated seats for {count} students.", "success")
    except (ValueError, IntegrityError) as e:
        db.session.rollback()
        flash(f"Allocation failed: {e}", "danger")
    return redirect(url_for("reports", exam_id=exam_id))

@app.route("/student-search", methods=["GET", "POST"])
@role_required("student", "admin")
def student_search():
    roll = current_user.roll_no if current_user.role == "student" else ""
    if request.method == "POST":
        entered = request.form.get("roll_no", "").strip()
        if current_user.role == "student" and entered.casefold() != (current_user.roll_no or "").casefold():
            flash("Student login can search only its linked roll number.", "danger")
            roll = ""
        else:
            roll = entered
    allocations = []
    if roll:
        allocations = SeatingAllocation.query.join(Student).filter(Student.roll_no.ilike(roll)).order_by(SeatingAllocation.id.desc()).all()
    return render_template("student_search.html", allocations=allocations, search_roll=roll)

@app.route("/reports")
@role_required("admin", "faculty")
def reports():
    exams = Exam.query.order_by(Exam.exam_date.desc()).all()
    exam_id = request.args.get("exam_id", type=int)
    selected = db.session.get(Exam, exam_id) if exam_id else (exams[0] if exams else None)
    allocations = SeatingAllocation.query.filter_by(exam_id=selected.id).join(Student).join(Room).order_by(Room.room_no, SeatingAllocation.bench_no, SeatingAllocation.seat_on_bench).all() if selected else []
    return render_template("reports.html", exams=exams, selected_exam=selected, allocations=allocations)

def report_data(exam_id):
    exam = db.session.get(Exam, exam_id)
    if not exam:
        return None, []
    allocations = SeatingAllocation.query.filter_by(exam_id=exam.id).join(Student).join(Room).order_by(Room.room_no, SeatingAllocation.bench_no, SeatingAllocation.seat_on_bench).all()
    return exam, allocations

@app.route("/reports/<int:exam_id>/excel")
@role_required("admin", "faculty")
def export_excel(exam_id):
    exam, allocations = report_data(exam_id)
    if not exam:
        flash("Exam not found.", "danger")
        return redirect(url_for("reports"))
    rows = [{"Exam": exam.name, "Subject": exam.subject, "Date": exam.exam_date,
        "Roll Number": a.student.roll_no, "Name": a.student.name, "Branch": a.student.branch,
        "Semester": a.student.semester, "Room": a.room.room_no, "Bench": a.bench_no,
        "Row": a.row_no, "Column": a.col_no, "Seat on Bench": a.seat_on_bench} for a in allocations]
    attendance = [{"Roll Number": a.student.roll_no, "Name": a.student.name, "Branch": a.student.branch,
        "Room": a.room.room_no, "Bench": a.bench_no, "Present / Signature": ""} for a in allocations]
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, index=False, sheet_name="Seating")
        pd.DataFrame(attendance).to_excel(writer, index=False, sheet_name="Attendance")
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f"exam_{exam_id}_seating.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/reports/<int:exam_id>/pdf")
@role_required("admin", "faculty")
def export_pdf(exam_id):
    exam, allocations = report_data(exam_id)
    if not exam:
        flash("Exam not found.", "danger")
        return redirect(url_for("reports"))
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 10, "Exam Seating Arrangement Report", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", size=9)
    pdf.cell(0, 7, f"Exam: {exam.name} | Subject: {exam.subject} | Date: {exam.exam_date}", new_x="LMARGIN", new_y="NEXT")
    headers = ["Roll No.", "Name", "Branch", "Room", "Bench", "Row", "Col", "Seat"]
    widths = [30, 55, 30, 25, 20, 18, 18, 18]
    pdf.set_font("Helvetica", "B", 8)
    for header, width in zip(headers, widths):
        pdf.cell(width, 8, header, border=1, align="C")
    pdf.ln()
    pdf.set_font("Helvetica", size=8)
    for a in allocations:
        values = [a.student.roll_no, a.student.name, a.student.branch, a.room.room_no,
                  str(a.bench_no), str(a.row_no), str(a.col_no), str(a.seat_on_bench)]
        for value, width in zip(values, widths):
            safe = str(value).encode("latin-1", "replace").decode("latin-1")
            pdf.cell(width, 7, safe[:30], border=1)
        pdf.ln()
    data = bytes(pdf.output())
    return send_file(io.BytesIO(data), as_attachment=True, download_name=f"exam_{exam_id}_seating.pdf", mimetype="application/pdf")

@app.errorhandler(413)
def too_large(_error):
    flash("File too large. Maximum upload size is 8 MB.", "danger")
    return redirect(url_for("upload"))

if __name__ == "__main__":
    app.run(debug=True)
