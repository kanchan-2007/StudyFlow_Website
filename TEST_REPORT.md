# StudyFlow Test Report

## Static checks completed in the build environment
- Python syntax compilation: passed for `app.py`, `create_admin.py`, and `test_app.py`.
- ZIP archive creation/integrity: checked after packaging.
- Test cases included in `test_app.py`: registration and verification, login, per-user data isolation, cross-account ownership checks, password reset, admin authorization, login/logout history, and task/timetable actions.

## Runtime tests
- Automated Flask tests could not be executed in the build environment because Flask is not installed and package installation was blocked by unavailable network access.
- Do not treat the test suite as passed until it is run locally after installing `requirements.txt`.

## Run locally
```bash
python -m pip install -r requirements.txt
python -m unittest -v
```

## Manual admin setup
Run `python create_admin.py` (or `create_admin.bat` on Windows), then start the application and sign in with the admin account. The admin dashboard is at `/admin`.

## Email delivery
SMTP-backed verification and password reset require valid SMTP environment variables. Without SMTP, development-only links are shown for local testing; do not deploy that fallback publicly.
