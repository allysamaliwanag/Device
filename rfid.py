import tkinter as tk
from tkinter import ttk, messagebox
import mysql.connector
import datetime
import time

nfc_tag_disabled = {}
last_scan_time = {}
spam_scan_threshold = 60  # Adjust this value as needed

# Function to clear the result
def clear_result():
    result_label.config(text="")
    name_label.config(text="Name:")
    role_label.config(text="Role:")
    image_label.config(image=None)
    text_entry.delete(0, "end")
    text_entry.config(state=tk.NORMAL)

# Function to record time in
def record_time_in(conn, name, role, nfc_id, student_id):
    current_time = datetime.datetime.now()
    formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.cursor()

    cursor.execute("SELECT attendance, grade_level, section, email FROM student WHERE studentID = %s", (student_id,))
    student_info = cursor.fetchone()

    if student_info and student_info[0] == "Absent":
        cursor.execute("UPDATE student SET attendance = %s WHERE studentID = %s", ("Present", student_id))
        conn.commit()

        cursor.execute("INSERT INTO logs (nfcTag, timeIn, name, role, status) VALUES (%s, %s, %s, %s, %s)",
                       (nfc_id, formatted_time, name, role, "Got in school"))
        conn.commit()

        cursor.execute("INSERT INTO attendance_records (studentID, name, email, grade_level, date, status, section) "
                       "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                       (student_id, name, student_info[3], student_info[1], formatted_time, "Present", student_info[2]))
        conn.commit()

        result_label.config(text=f"Time In recorded for {role} (Got in school)")
    else:
        status = student_info[0]
        if status == "Got out of school but not dismissed yet" and current_time.time() < datetime.time(15, 0, 0):
            status = "Got back in school"
            cursor.execute("UPDATE logs SET timeOut = NULL WHERE nfcTag = %s AND DATE(timeIn) = CURDATE()", (nfc_id,))
        result_label.config(text=f"Time In recorded for {role} ({status})")

    text_entry.delete(0, "end")
    text_entry.config(state=tk.DISABLED)
    root.after(5000, clear_result)

# Function to record time out
def record_time_out(conn, name, role, nfc_id, student_id):
    current_time = datetime.datetime.now()
    formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")  # Corrected time formatting

    cursor = conn.cursor()

    cursor.execute("SELECT attendance FROM student WHERE nfcTag = %s", (nfc_id,))
    attendance_result = cursor.fetchone()

    if attendance_result and attendance_result[0] != "":
        status = attendance_result[0]

        if current_time.time() < datetime.time(14, 30, 0):
            status = "Possible Cutting Classes"
            cursor.execute("INSERT INTO reports (name, section, timestamp, description, role, status, grade_level) "
                           "VALUES (%s, %s, NOW(), %s, %s, %s, %s)",
                           (name, "student_section", "Possible Cutting Classes", role, status, "student_grade_level"))
            conn.commit()
        else:
            if current_time.time() >= datetime.time(15, 0, 0):
                status = "Dismissed from school"
                cursor.execute("UPDATE attendance_records SET status = %s WHERE studentID = %s AND date = CURDATE()",
                               (status, student_id))
                conn.commit()
            else:
                status = "Got out of school but not dismissed yet"

        cursor.execute("UPDATE student SET attendance = %s WHERE nfcTag = %s", ("Absent", nfc_id))
        conn.commit()

        cursor.execute("UPDATE logs SET timeOut = %s, status = %s WHERE nfcTag = %s AND DATE(timeIn) = CURDATE()",
                       (formatted_time, status, nfc_id))
        conn.commit()
        result_label.config(text=f"Time Out recorded for {role} ({status})")

    text_entry.delete(0, "end")
    text_entry.config(state=tk.DISABLED)
    root.after(5000, clear_result)

# Function to update attendance
def update_attendance(conn, role, nfc_id, status):
    cursor = conn.cursor()

    if status in ("Got in time", "In school but late", "Got out of school but not dismissed yet", "Got back in school"):
        attendance = "Present"
    else:
        attendance = "Absent"

    cursor.execute(f"UPDATE {role} SET attendance = %s WHERE nfcTag = %s", (attendance, nfc_id))
    conn.commit()

# Function to fetch info from the database
def fetch_info_from_db(*args):
    entered_nfc_id = text_entry.get()

    if not entered_nfc_id:
        return

    current_time = time.time()

    if entered_nfc_id in nfc_tag_disabled:
        if current_time - nfc_tag_disabled[entered_nfc_id] < 60:
            result_label.config(text="NFC Tag is currently disabled due to spam scan.")
            text_entry.delete(0, "end")
            return
        else:
            del nfc_tag_disabled[entered_nfc_id]

    # Check for spam scans based on the time interval between scans
    if entered_nfc_id in last_scan_time:
        time_since_last_scan = current_time - last_scan_time[entered_nfc_id]
        if time_since_last_scan < spam_scan_threshold:
            result_label.config(text="NFC Tag is currently disabled due to spam scan.")
            text_entry.delete(0, "end")
            nfc_tag_disabled[entered_nfc_id] = current_time
            return
    else:
        last_scan_time[entered_nfc_id] = current_time

    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="",  # Enter your password here
            database="rfid"
        )
    except mysql.connector.Error as e:
        result_label.config(text="Database connection error")
        return

    cursor = conn.cursor()
    text_entry.delete(0, "end")

    cursor.execute("SELECT id, name, role, attendance, studentID FROM student WHERE nfcTag=%s", (entered_nfc_id,))
    student_result = cursor.fetchone()

    if student_result is None:
        cursor.execute("SELECT id, name, role, attendance, teacherID FROM teacher WHERE nfcTag=%s", (entered_nfc_id,))
        teacher_result = cursor.fetchone()

        if teacher_result:
            student_id, name, role, attendance, student_id = teacher_result
        else:
            result_label.config(text="NFC ID not found")
            name_label.config(text="Name:")
            role_label.config(text="Role:")
            conn.close()
            return
    else:
        student_id, name, role, attendance, student_id = student_result

    name_label.config(text=f"Name: {name}")
    role_label.config(text=f"Role: {role}")
    if attendance == "Absent":
        result_label.config(text="NFC Tag Scanned (Absent) - Recording Time In")
        record_time_in(conn, name, role, entered_nfc_id, student_id)
    elif attendance == "Present":
        result_label.config(text="NFC Tag Scanned (Present) - Recording Time Out")
        record_time_out(conn, name, role, entered_nfc_id, student_id)
    else:
        result_label.config(text="NFC Tag Scanned")

# Function to handle the window close event
def on_close():
    if messagebox.askokcancel("Quit", "Do you want to quit?"):
        root.destroy()

# Create the main window
root = tk.Tk()
root.title("Alitagtag Senior High School")

# Apply a dark green theme
root.configure(bg="#006400")

# Make the application full screen
root.attributes('-fullscreen', True)

style = ttk.Style()
style.configure("TFrame", background="#006400")
style.configure("TLabel", background="#006400", foreground="#fff", font=("Helvetica", 12, "bold"))
style.configure("TButton", background="#333", foreground="#fff", font=("Helvetica", 12, "bold"))

main_frame = ttk.Frame(root, padding=20, style="TFrame")
main_frame.pack(expand=True)

nfc_id_label = ttk.Label(main_frame, text="NFC ID:", style="TLabel")
nfc_id_label.grid(row=0, column=0, padx=10, pady=10, sticky=tk.W)

text_entry = ttk.Entry(main_frame, width=30)
text_entry.grid(row=0, column=1, padx=10, pady=10, sticky=tk.W)

text_entry.bind("<Return>", fetch_info_from_db)
text_entry.focus()

name_label = ttk.Label(main_frame, text="Name:", style="TLabel")
name_label.grid(row=1, column=0, padx=10, pady=10, sticky=tk.W)

role_label = ttk.Label(main_frame, text="Role:", style="TLabel")
role_label.grid(row=2, column=0, padx=10, pady=10, sticky=tk.W)

result_label = ttk.Label(main_frame, text="", font=("Helvetica", 14, "bold"), style="TLabel")
result_label.grid(row=3, column=0, columnspan=2, padx=10, pady=10, sticky=tk.W)

image_frame = ttk.Frame(main_frame)
image_frame.grid(row=1, column=2, rowspan=3, padx=10, pady=10, sticky=(tk.W, tk.E, tk.N, tk.S))

image_label = ttk.Label(image_frame)
image_label.pack(fill=tk.BOTH, expand=True)

close_button = ttk.Button(root, text="Close", style="TButton", command=on_close)
close_button.pack(side=tk.RIGHT, padx=20, pady=20)

root.protocol("WM_DELETE_WINDOW", on_close)
root.mainloop()
