from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from email.message import EmailMessage
import sqlite3, os, smtplib, re
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'local-studyflow-change-this-secret')
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                  TOKEN_MAX_AGE=int(os.environ.get('TOKEN_MAX_AGE', '3600')))
DB_PATH = os.path.join(os.path.dirname(__file__), 'study_planner.db')
DAYS = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    with db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 0, role TEXT NOT NULL DEFAULT 'student',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT NOT NULL,
            color TEXT NOT NULL DEFAULT '#4f46e5', target_hours REAL NOT NULL DEFAULT 3,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, title TEXT NOT NULL, subject_id INTEGER,
            due_date TEXT, priority TEXT NOT NULL DEFAULT 'Medium', done INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE SET NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS timetable (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, day TEXT NOT NULL,
            start_time TEXT NOT NULL, end_time TEXT NOT NULL, subject_id INTEGER,
            topic TEXT NOT NULL DEFAULT '', FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE SET NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS login_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, login_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            logout_at TEXT, FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)''')
        # Upgrade older versions in place while retaining the existing project structure/data.
        user_cols = {r['name'] for r in conn.execute('PRAGMA table_info(users)')}
        if 'role' not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'student'")
        for table in ('subjects','tasks','timetable'):
            cols = {r['name'] for r in conn.execute(f'PRAGMA table_info({table})')}
            if 'user_id' not in cols:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_subjects_user ON subjects(user_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_timetable_user ON timetable(user_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_login_history_user ON login_history(user_id)')


def serializer():
    return URLSafeTimedSerializer(app.secret_key, salt='studyflow-account-tokens')


def current_user():
    uid = session.get('user_id')
    if not uid: return None
    with db() as conn:
        return conn.execute('SELECT id,name,email,verified,role FROM users WHERE id=?', (uid,)).fetchone()


def login_required():
    user = current_user()
    if not user:
        flash('Please log in to access your personal study planner.', 'error')
        return None
    if not user['verified']:
        session.clear()
        flash('Please verify your email before logging in.', 'error')
        return None
    return user


def send_email(to, subject, body):
    host = os.environ.get('SMTP_HOST')
    if not host:
        # Safe local-demo fallback: link is displayed only in development, never represented as email sent.
        app.logger.warning('SMTP is not configured. Development email for %s:\n%s', to, body)
        return False
    msg = EmailMessage(); msg['Subject'] = subject
    msg['From'] = os.environ.get('SMTP_FROM', os.environ.get('SMTP_USER', 'studyflow@localhost'))
    msg['To'] = to; msg.set_content(body)
    port = int(os.environ.get('SMTP_PORT', '587'))
    with smtplib.SMTP(host, port, timeout=10) as server:
        server.starttls()
        if os.environ.get('SMTP_USER'):
            server.login(os.environ['SMTP_USER'], os.environ.get('SMTP_PASSWORD', ''))
        server.send_message(msg)
    return True


def issue_token(kind, user_id, email):
    return serializer().dumps({'kind':kind,'uid':user_id,'email':email})


def read_token(token, kind):
    try:
        data = serializer().loads(token, max_age=app.config['TOKEN_MAX_AGE'])
        if data.get('kind') != kind: return None
        return data
    except (BadSignature, SignatureExpired, TypeError):
        return None


def send_action_link(user, kind):
    token = issue_token(kind, user['id'], user['email'])
    endpoint = 'verify_email' if kind == 'verify' else 'reset_password'
    link = url_for(endpoint, token=token, _external=True)
    if kind == 'verify':
        subject, body = 'Verify your StudyFlow email', f'Hello {user["name"]},\n\nVerify your StudyFlow email using this link (expires in one hour):\n{link}\n'
    else:
        subject, body = 'Reset your StudyFlow password', f'Hello {user["name"]},\n\nReset your StudyFlow password using this link (expires in one hour):\n{link}\nIf you did not request this, ignore this message.\n'
    try:
        sent = send_email(user['email'], subject, body)
    except (OSError, smtplib.SMTPException) as exc:
        app.logger.exception('Email delivery failed: %s', exc)
        sent = False
    return link, sent


@app.context_processor
def inject_user():
    return {'logged_in_user': current_user()}

@app.route('/')
def index():
    user = login_required()
    if not user: return redirect(url_for('login'))
    with db() as conn:
        subjects = conn.execute('SELECT * FROM subjects WHERE user_id=? ORDER BY name',(user['id'],)).fetchall()
        tasks = conn.execute('''SELECT tasks.*, subjects.name AS subject_name FROM tasks
            LEFT JOIN subjects ON tasks.subject_id=subjects.id AND subjects.user_id=tasks.user_id
            WHERE tasks.user_id=? ORDER BY tasks.done ASC,
            CASE tasks.priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END,
            tasks.due_date IS NULL,tasks.due_date''',(user['id'],)).fetchall()
        sessions = conn.execute('''SELECT timetable.*,subjects.name AS subject_name,subjects.color FROM timetable
            LEFT JOIN subjects ON timetable.subject_id=subjects.id AND subjects.user_id=timetable.user_id
            WHERE timetable.user_id=? ORDER BY CASE day WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2
            WHEN 'Wednesday' THEN 3 WHEN 'Thursday' THEN 4 WHEN 'Friday' THEN 5 WHEN 'Saturday' THEN 6 ELSE 7 END,start_time''',(user['id'],)).fetchall()
    total_tasks = len(tasks); completed = sum(1 for t in tasks if t['done'])
    progress = round(completed/total_tasks*100) if total_tasks else 0
    grouped = {day:[] for day in DAYS}
    for s in sessions: grouped[s['day']].append(s)
    return render_template('index.html',subjects=subjects,tasks=tasks,sessions=sessions,grouped=grouped,
        days=DAYS,total_tasks=total_tasks,completed=completed,progress=progress)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        name=request.form.get('name','').strip(); email=request.form.get('email','').strip().lower()
        password=request.form.get('password',''); confirm=request.form.get('confirm_password','')
        if not name or len(name)>100 or not EMAIL_RE.match(email):
            flash('Enter your name and a valid email address.','error')
        elif len(password)<8:
            flash('Password must be at least 8 characters.','error')
        elif password != confirm:
            flash('Passwords do not match.','error')
        else:
            try:
                with db() as conn:
                    cur=conn.execute('INSERT INTO users(name,email,password_hash) VALUES(?,?,?)',
                                     (name,email,generate_password_hash(password)))
                    uid=cur.lastrowid
                with db() as conn:
                    # A new account starts with an empty, private workspace.
                    conn.execute('INSERT INTO subjects(user_id,name,color,target_hours) VALUES(?,?,?,?)',(uid,'Mathematics','#4f46e5',3))
                    user=conn.execute('SELECT id,name,email FROM users WHERE id=?',(uid,)).fetchone()
                link,sent=send_action_link(user,'verify')
                flash('Account created. Check your email to verify it.' if sent else 'Account created. SMTP is not configured; use the development verification link below.','success')
                return render_template('auth.html', mode='register', development_link=None if sent else link)
            except sqlite3.IntegrityError:
                flash('An account with this email already exists.','error')
    return render_template('auth.html',mode='register',development_link=None)

@app.route('/verify/<token>')
def verify_email(token):
    data=read_token(token,'verify')
    if not data:
        flash('That verification link is invalid or expired. Please register again or request a new link.','error')
        return redirect(url_for('login'))
    with db() as conn:
        cur=conn.execute('UPDATE users SET verified=1 WHERE id=? AND email=?',(data['uid'],data['email']))
    if cur.rowcount:
        flash('Email verified. You can now log in.','success')
    else: flash('Account could not be verified.','error')
    return redirect(url_for('login'))

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        with db() as conn: user=conn.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
        if not user or not check_password_hash(user['password_hash'],password):
            flash('Invalid email or password.','error')
        elif not user['verified']:
            flash('Please verify your email before logging in.','error')
            _,sent=send_action_link(user,'verify')
            if not sent:
                flash('SMTP is not configured; ask the developer to check the server log for the local verification link.','error')
        else:
            session.clear(); session['user_id']=user['id']
            with db() as conn:
                cur = conn.execute('INSERT INTO login_history(user_id) VALUES(?)', (user['id'],))
                session['login_event_id'] = cur.lastrowid
            flash(f'Welcome back, {user["name"]}.','success')
            return redirect(url_for('admin_dashboard') if user['role']=='admin' else url_for('index'))
    return render_template('auth.html',mode='login',development_link=None)

@app.route('/logout',methods=['POST'])
def logout():
    event_id=session.get('login_event_id')
    if event_id:
        with db() as conn: conn.execute('UPDATE login_history SET logout_at=CURRENT_TIMESTAMP WHERE id=? AND logout_at IS NULL',(event_id,))
    session.clear(); flash('You have been logged out.','success'); return redirect(url_for('login'))

@app.route('/forgot-password',methods=['GET','POST'])
def forgot_password():
    development_link=None
    if request.method=='POST':
        email=request.form.get('email','').strip().lower()
        with db() as conn: user=conn.execute('SELECT id,name,email FROM users WHERE email=?',(email,)).fetchone()
        # Same outward response whether the account exists or not.
        flash('If an account exists for that email, password-reset instructions have been sent.','success')
        if user:
            development_link,sent=send_action_link(user,'reset')
            if sent: development_link=None
        return render_template('forgot_password.html',development_link=development_link)
    return render_template('forgot_password.html',development_link=None)

@app.route('/reset-password/<token>',methods=['GET','POST'])
def reset_password(token):
    data=read_token(token,'reset')
    if not data:
        flash('That reset link is invalid or expired. Request a new one.','error')
        return redirect(url_for('forgot_password'))
    with db() as conn: user=conn.execute('SELECT id,email FROM users WHERE id=? AND email=?',(data['uid'],data['email'])).fetchone()
    if not user: flash('Account not found.','error'); return redirect(url_for('forgot_password'))
    if request.method=='POST':
        password=request.form.get('password',''); confirm=request.form.get('confirm_password','')
        if len(password)<8: flash('Password must be at least 8 characters.','error')
        elif password!=confirm: flash('Passwords do not match.','error')
        else:
            with db() as conn: conn.execute('UPDATE users SET password_hash=? WHERE id=?',(generate_password_hash(password),user['id']))
            flash('Password updated. Please log in.','success'); return redirect(url_for('login'))
    return render_template('reset_password.html')

@app.route('/subjects',methods=['POST'])
def add_subject():
    user=login_required()
    if not user: return redirect(url_for('login'))
    name=request.form.get('name','').strip(); color=request.form.get('color','#4f46e5')
    try: target=max(0.5,min(30,float(request.form.get('target_hours','3'))))
    except ValueError: target=3
    if not name: flash('Please enter a subject name.','error')
    else:
        with db() as conn: conn.execute('INSERT INTO subjects(user_id,name,color,target_hours) VALUES(?,?,?,?)',(user['id'],name,color,target))
        flash('Subject added.','success')
    return redirect(url_for('index')+'#tasks')

@app.route('/tasks',methods=['POST'])
def add_task():
    user=login_required()
    if not user: return redirect(url_for('login'))
    title=request.form.get('title','').strip(); subject_raw=request.form.get('subject_id',''); due_date=request.form.get('due_date') or None
    priority=request.form.get('priority','Medium')
    if priority not in ('Low','Medium','High'): priority='Medium'
    subject_id=None
    if subject_raw:
        try: candidate=int(subject_raw)
        except ValueError: candidate=-1
        with db() as conn: found=conn.execute('SELECT id FROM subjects WHERE id=? AND user_id=?',(candidate,user['id'])).fetchone()
        if not found: flash('Please choose one of your own subjects.','error'); return redirect(url_for('index')+'#tasks')
        subject_id=candidate
    if not title: flash('Please enter a task title.','error')
    else:
        with db() as conn: conn.execute('INSERT INTO tasks(user_id,title,subject_id,due_date,priority) VALUES(?,?,?,?,?)',(user['id'],title,subject_id,due_date,priority))
        flash('Study task added.','success')
    return redirect(url_for('index')+'#tasks')

@app.route('/tasks/<int:task_id>/toggle',methods=['POST'])
def toggle_task(task_id):
    user=login_required()
    if not user: return redirect(url_for('login'))
    with db() as conn: conn.execute('UPDATE tasks SET done=CASE WHEN done=0 THEN 1 ELSE 0 END WHERE id=? AND user_id=?',(task_id,user['id']))
    return redirect(url_for('index')+'#tasks')

@app.route('/tasks/<int:task_id>/delete',methods=['POST'])
def delete_task(task_id):
    user=login_required()
    if not user: return redirect(url_for('login'))
    with db() as conn: conn.execute('DELETE FROM tasks WHERE id=? AND user_id=?',(task_id,user['id']))
    flash('Task deleted if it belonged to your account.','success')
    return redirect(url_for('index')+'#tasks')

@app.route('/timetable/generate',methods=['POST'])
def generate_timetable():
    user=login_required()
    if not user: return redirect(url_for('login'))
    try:
        block_minutes=int(request.form.get('block_minutes','60')); blocks_per_day=int(request.form.get('blocks_per_day','3')); start_hour=int(request.form.get('start_hour','16'))
        if block_minutes not in (30,45,60,90,120): block_minutes=60
        blocks_per_day=max(1,min(6,blocks_per_day)); start_hour=max(6,min(21,start_hour))
    except ValueError: block_minutes,blocks_per_day,start_hour=60,3,16
    with db() as conn:
        subjects=conn.execute('SELECT * FROM subjects WHERE user_id=? ORDER BY target_hours DESC,name',(user['id'],)).fetchall()
        conn.execute('DELETE FROM timetable WHERE user_id=?',(user['id'],))
        if not subjects: flash('Add at least one subject before generating a timetable.','error'); return redirect(url_for('index')+'#dashboard')
        idx=0
        for day in DAYS[:6]:
            for block in range(blocks_per_day):
                subject=subjects[idx%len(subjects)]; start_m=start_hour*60+block*(block_minutes+15); end_m=start_m+block_minutes
                if end_m>22*60: break
                start=f'{start_m//60:02d}:{start_m%60:02d}'; end=f'{end_m//60:02d}:{end_m%60:02d}'
                topic='Focus session' if block==0 else ('Practice & revision' if block==1 else 'Review / exercises')
                conn.execute('INSERT INTO timetable(user_id,day,start_time,end_time,subject_id,topic) VALUES(?,?,?,?,?,?)',(user['id'],day,start,end,subject['id'],topic)); idx+=1
    flash('Your weekly timetable has been generated.','success'); return redirect(url_for('index')+'#dashboard')

@app.route('/timetable/clear',methods=['POST'])
def clear_timetable():
    user=login_required()
    if not user: return redirect(url_for('login'))
    with db() as conn: conn.execute('DELETE FROM timetable WHERE user_id=?',(user['id'],))
    flash('Timetable cleared.','success'); return redirect(url_for('index')+'#dashboard')



def admin_required():
    user = login_required()
    if not user:
        return None
    if user['role'] != 'admin':
        abort(403)
    return user

@app.route('/admin')
def admin_dashboard():
    admin = admin_required()
    if not admin:
        return redirect(url_for('login'))
    with db() as conn:
        users = conn.execute('''SELECT u.id,u.name,u.email,u.verified,u.role,u.created_at,
            (SELECT COUNT(*) FROM tasks t WHERE t.user_id=u.id) AS task_count,
            (SELECT COUNT(*) FROM tasks t WHERE t.user_id=u.id AND t.done=1) AS completed_count
            FROM users u ORDER BY u.created_at DESC''').fetchall()
        history = conn.execute('''SELECT h.id,h.login_at,h.logout_at,u.name,u.email
            FROM login_history h JOIN users u ON u.id=h.user_id ORDER BY h.id DESC LIMIT 100''').fetchall()
        totals = {
            'users': conn.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0],
            'tasks': conn.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],
            'logins': conn.execute('SELECT COUNT(*) FROM login_history').fetchone()[0],
            'unverified': conn.execute("SELECT COUNT(*) FROM users WHERE verified=0 AND role='student'").fetchone()[0]
        }
    return render_template('admin.html', users=users, history=history, totals=totals)

@app.route('/admin/user/<int:user_id>')
def admin_user_tasks(user_id):
    admin = admin_required()
    if not admin:
        return redirect(url_for('login'))
    with db() as conn:
        user = conn.execute("SELECT id,name,email,verified,created_at FROM users WHERE id=? AND role='student'", (user_id,)).fetchone()
        if not user: abort(404)
        tasks = conn.execute('''SELECT t.*,s.name AS subject_name FROM tasks t
            LEFT JOIN subjects s ON s.id=t.subject_id AND s.user_id=t.user_id
            WHERE t.user_id=? ORDER BY t.done,t.due_date''', (user_id,)).fetchall()
        subjects = conn.execute('SELECT name,color,target_hours FROM subjects WHERE user_id=? ORDER BY name',(user_id,)).fetchall()
    return render_template('admin_user.html', user=user, tasks=tasks, subjects=subjects)

if __name__=='__main__':
    init_db()
    app.run(debug=os.environ.get('FLASK_DEBUG')=='1',host='127.0.0.1',port=5000)
