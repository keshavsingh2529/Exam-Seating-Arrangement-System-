from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")
    roll_no = db.Column(db.String(40), nullable=True)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    roll_no = db.Column(db.String(40), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    branch = db.Column(db.String(60), nullable=False)
    semester = db.Column(db.String(20), nullable=False)

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_no = db.Column(db.String(40), unique=True, nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    rows = db.Column(db.Integer, nullable=False)
    cols = db.Column(db.Integer, nullable=False)
    benches = db.Column(db.Integer, nullable=False)

class Exam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    subject = db.Column(db.String(120), nullable=False)
    exam_date = db.Column(db.String(10), nullable=False)
    start_time = db.Column(db.String(5), nullable=False)
    end_time = db.Column(db.String(5), nullable=False)
    semester = db.Column(db.String(20), nullable=False, default="All")

class SeatingAllocation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey("room.id"), nullable=False)
    bench_no = db.Column(db.Integer, nullable=False)
    row_no = db.Column(db.Integer, nullable=False)
    col_no = db.Column(db.Integer, nullable=False)
    seat_on_bench = db.Column(db.Integer, nullable=False)
    exam = db.relationship("Exam", backref=db.backref("allocations", cascade="all, delete-orphan"))
    student = db.relationship("Student")
    room = db.relationship("Room")
    __table_args__ = (
        db.UniqueConstraint("exam_id", "student_id", name="uq_exam_student"),
        db.UniqueConstraint("exam_id", "room_id", "bench_no", "seat_on_bench", name="uq_exam_bench_seat"),
    )
