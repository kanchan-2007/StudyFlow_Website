# StudyFlow — Smart Study Planner

A Flask-based study planner with a horizontal, slide-style green-and-white interface.

## Features
- Account registration and login with salted password hashing
- Email verification links with one-hour expiry
- Password reset links with one-hour expiry
- Private subjects, tasks, and timetable for each user
- Ownership checks on task changes and subject selection
- Dashboard progress and weekly timetable generator
- Admin dashboard for registered student accounts, verification status, task totals, and recent login/logout history
- Admin-only per-user task and subject review
- Responsive Home, Dashboard, Tasks, and About navigation (Contact page removed)
- SQLite database created next to `app.py`; existing databases are upgraded in place

## Run on Windows
1. Extract the ZIP and open the `Smart_Study_Planner` folder.
2. Double-click `run_windows.bat`.
3. Open http://127.0.0.1:5000 and register an account.
4. For local demo use without SMTP, the app displays a development-only verification/reset link on the relevant page. This fallback is intended only for a local demonstration.
5. To create an administrator, stop and close the app terminal, open a second terminal in this folder, and run `python create_admin.py` (or double-click `create_admin.bat`). Follow the prompts. Start the app again and log in with the admin email/password; you will be redirected to `/admin`.
6. Keep the terminal open while using the site. Press `Ctrl+C` to stop it.

If needed, install dependencies and run manually:
```bash
python -m pip install -r requirements.txt
python app.py
```

## Configure real email delivery
Set these environment variables before starting the app:
- `SMTP_HOST` — SMTP server hostname
- `SMTP_PORT` — usually `587`
- `SMTP_USER` — SMTP account username (optional if the server does not require login)
- `SMTP_PASSWORD` — SMTP account password or app password
- `SMTP_FROM` — sender email address
- `SECRET_KEY` — a long, random secret used to sign sessions and account links

When SMTP is configured, verification and reset links are sent by email and are not shown in the page. Never use the development secret or expose development links on a public server. Use HTTPS and a strong `SECRET_KEY` before deployment. This project is configured for local demonstration, not production hosting.

## Test
From this folder, run:
```bash
python -m unittest -v
```
The test suite covers registration/verification, login, account data isolation, cross-account ownership checks, password reset, admin access control, login/logout history, and timetable/task actions. Run it in an environment where `requirements.txt` has been installed.

## Data and migration
The SQLite file `study_planner.db` is created automatically. Back it up before replacing/upgrading a database. Old shared demo rows are not assigned to any new account; each account receives its own starter subject and private records.


## Admin privacy and access
The admin dashboard is available only to accounts with the `admin` role. Create/promote an admin through the local `create_admin.py` script; never add a public admin-registration route. The dashboard shows account email addresses and user activity, so keep it private and do not expose this local demo directly to the public internet. Login history records successful sign-ins and logout timestamps when a user logs out normally.
