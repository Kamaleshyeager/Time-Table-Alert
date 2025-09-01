# Timetable Reminder Bot

A Python bot that reminds you before each class based on your timetable.

## Why This Project?
At **Vellore Institute of Technology (VIT)**, the timetable system can get confusing - 
class **venues, faculty names, and slot codes** are different for every student.  
Most students end up checking screenshots or PDFs multiple times a day just to confirm their next class.  

This project solves that problem by sending **automatic reminders** before each class.  
It makes it easy to know *what class, where, and when* without the need to search through messy timetables.

## Features
- Reads and stores your personal timetable slots
- Sends reminders before each class
- Uses APScheduler for accurate scheduling
- Fully customizable timetable (fits VIT’s slot system)
- Helps avoid confusion caused by varying slots, venues, and faculty names

## Requirements
- Python 3.9+
- Virtual environment (`.venv`)
- Dependencies listed in `requirements.txt`

## Setup

1. **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd timetable-bot
    ```

2. **Create and activate virtual environment (Windows PowerShell):**
    ```powershell
    python -m venv .venv
    .\.venv\Scripts\Activate
    ```

3. **Install dependencies:**
    ```powershell
    pip install -r requirements.txt
    ```

4. **Run the bot:**
    ```powershell
    python timetable_bot.py
    ```

## Project Structure
timetable-bot/
│
├── timetable_bot.py # Main bot script (reads timetable and sends reminders)
├── requirements.txt # Python dependencies
├── .gitignore # Files and folders to ignore in Git
└── README.md # Project documentation
