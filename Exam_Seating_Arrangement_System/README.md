# Exam Seating Arrangement System

## Demo accounts (local testing)
- Admin: `admin` / `admin123`
- Student: `student` / `student123` (linked roll number CSE001)
- Faculty: `faculty` / `faculty123`

## Run in VS Code (Windows)
```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000 in your browser.

## First demo
1. Log in as admin.
2. Create an exam. Use semester `5`, a future date, and valid start/end times.
3. Click Generate Seats.
4. View Reports and download PDF/Excel.
5. Log in as student to search their own roll number CSE001.
6. Log in as faculty to view reports/attendance.

## CSV columns
Students: `roll_no,name,branch,semester`
Rooms: `room_no,capacity,rows,cols,benches`
Sample CSV files are in `sample_data`.

## Notes
This is a college prototype. Seating attempts to place different branches together on a two-seat bench when possible; perfect separation is impossible when branch counts or seat counts make it mathematically impossible. Data is stored in local SQLite. Demo credentials and Flask debug mode are for local development only; change them before real deployment.
