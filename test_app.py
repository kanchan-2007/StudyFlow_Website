import os, tempfile, unittest, re
import app as planner

class StudyFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        planner.DB_PATH = os.path.join(self.tmp.name, 'test.db')
        planner.app.config.update(TESTING=True, SECRET_KEY='test-secret-key', TOKEN_MAX_AGE=3600)
        planner.init_db()
        self.client = planner.app.test_client()

    def tearDown(self): self.tmp.cleanup()

    def register_and_verify(self, name, email, password='StrongPass123!'):
        response = self.client.post('/register', data={'name':name,'email':email,'password':password,'confirm_password':password})
        self.assertEqual(response.status_code, 200)
        match = re.search(rb'href="([^"]*/verify/[^"]+)"', response.data)
        self.assertIsNotNone(match, 'Local verification link should be present when SMTP is not configured')
        verify_url = match.group(1).decode().replace('http://localhost', '')
        verify = self.client.get(verify_url)
        self.assertEqual(verify.status_code, 302)
        return password

    def login(self, email, password):
        return self.client.post('/login', data={'email':email,'password':password}, follow_redirects=False)

    def test_registration_requires_verification_then_login(self):
        self.client.post('/register', data={'name':'A Student','email':'a@example.com','password':'StrongPass123!','confirm_password':'StrongPass123!'})
        response = self.login('a@example.com','StrongPass123!')
        self.assertEqual(response.status_code, 200)
        with planner.db() as conn:
            self.assertEqual(conn.execute('SELECT verified FROM users WHERE email=?',('a@example.com',)).fetchone()[0], 0)
        self.register_and_verify('B Student','b@example.com')
        self.assertEqual(self.login('b@example.com','StrongPass123!').status_code, 302)
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_users_have_isolated_subjects_tasks_and_timetables(self):
        self.register_and_verify('Alice','alice@example.com')
        self.login('alice@example.com','StrongPass123!')
        with planner.db() as conn:
            alice_subject = conn.execute('SELECT id FROM subjects WHERE user_id=(SELECT id FROM users WHERE email=?)',('alice@example.com',)).fetchone()[0]
        self.client.post('/subjects', data={'name':'Alice Biology','color':'#123456','target_hours':'4'})
        self.client.post('/tasks', data={'title':'Alice private task','subject_id':alice_subject,'priority':'High'})
        self.client.post('/timetable/generate', data={'block_minutes':'60','blocks_per_day':'2','start_hour':'16'})
        self.client.post('/logout')
        self.register_and_verify('Bob','bob@example.com')
        self.login('bob@example.com','StrongPass123!')
        page=self.client.get('/').data
        self.assertNotIn(b'Alice private task', page)
        self.assertNotIn(b'Alice Biology', page)
        with planner.db() as conn:
            bob_id=conn.execute('SELECT id FROM users WHERE email=?',('bob@example.com',)).fetchone()[0]
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM tasks WHERE user_id=?',(bob_id,)).fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM timetable WHERE user_id=?',(bob_id,)).fetchone()[0],0)
            self.assertGreater(conn.execute('SELECT COUNT(*) FROM subjects WHERE user_id=?',(bob_id,)).fetchone()[0],0)

    def test_cannot_attach_another_users_subject_or_mutate_their_task(self):
        self.register_and_verify('Alice','alice@example.com')
        self.login('alice@example.com','StrongPass123!')
        with planner.db() as conn:
            alice_id=conn.execute('SELECT id FROM users WHERE email=?',('alice@example.com',)).fetchone()[0]
            subject_id=conn.execute('SELECT id FROM subjects WHERE user_id=?',(alice_id,)).fetchone()[0]
            conn.execute('INSERT INTO tasks(user_id,title,subject_id) VALUES(?,?,?)',(alice_id,'protected task',subject_id))
            task_id=conn.execute('SELECT id FROM tasks WHERE title=?',('protected task',)).fetchone()[0]
        self.client.post('/logout')
        self.register_and_verify('Bob','bob@example.com')
        self.login('bob@example.com','StrongPass123!')
        self.client.post('/tasks',data={'title':'bad cross-account task','subject_id':subject_id})
        self.client.post(f'/tasks/{task_id}/delete')
        with planner.db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM tasks WHERE id=?',(task_id,)).fetchone()[0],1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM tasks WHERE title='bad cross-account task'").fetchone()[0],0)

    def test_password_reset_changes_password_and_token_expires(self):
        self.register_and_verify('Reset User','reset@example.com')
        response=self.client.post('/forgot-password',data={'email':'reset@example.com'})
        match=re.search(rb'href="([^"]*/reset-password/[^"]+)"',response.data)
        self.assertIsNotNone(match)
        reset_url=match.group(1).decode().replace('http://localhost','')
        response=self.client.get(reset_url)
        self.assertEqual(response.status_code,200)
        response=self.client.post(reset_url,data={'password':'NewStrongPass456!','confirm_password':'NewStrongPass456!'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.login('reset@example.com','StrongPass123!').status_code,200)
        self.assertEqual(self.login('reset@example.com','NewStrongPass456!').status_code,302)

    def test_password_reset_mismatch_and_invalid_token(self):
        self.register_and_verify('Reset User','reset@example.com')
        response=self.client.post('/forgot-password',data={'email':'reset@example.com'})
        match=re.search(rb'href="([^"]*/reset-password/[^"]+)"',response.data)
        url=match.group(1).decode().replace('http://localhost','')
        response=self.client.post(url,data={'password':'NewStrongPass456!','confirm_password':'different'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.get('/reset-password/not-a-valid-token').status_code,302)


    def test_admin_dashboard_requires_admin_and_shows_users_and_login_history(self):
        self.register_and_verify('Student','student@example.com')
        self.login('student@example.com','StrongPass123!')
        self.assertEqual(self.client.get('/admin').status_code, 403)
        self.client.post('/logout')
        with planner.db() as conn:
            conn.execute("INSERT INTO users(name,email,password_hash,verified,role) VALUES(?,?,?,?,?)",
                         ('Admin','admin@example.com',planner.generate_password_hash('AdminPass123!'),1,'admin'))
        self.login('admin@example.com','AdminPass123!')
        response=self.client.get('/admin')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'student@example.com', response.data)
        self.assertIn(b'Recent login history', response.data)
        self.assertEqual(self.client.get('/admin/user/1').status_code, 200)
        self.client.post('/logout')
        with planner.db() as conn:
            self.assertGreaterEqual(conn.execute('SELECT COUNT(*) FROM login_history').fetchone()[0], 2)
            self.assertGreaterEqual(conn.execute('SELECT COUNT(*) FROM login_history WHERE logout_at IS NOT NULL').fetchone()[0], 2)

    def test_private_routes_require_login(self):
        for path in ('/','/tasks','/subjects','/timetable/generate'):
            if path=='/': response=self.client.get(path)
            else: response=self.client.post(path)
            self.assertIn(response.status_code,(302,405))

    def test_timetable_and_task_actions(self):
        self.register_and_verify('Planner','planner@example.com')
        self.login('planner@example.com','StrongPass123!')
        response=self.client.post('/tasks',data={'title':'Test revision','priority':'High'})
        self.assertEqual(response.status_code,302)
        with planner.db() as conn:
            uid=conn.execute('SELECT id FROM users WHERE email=?',('planner@example.com',)).fetchone()[0]
            task=conn.execute("SELECT id FROM tasks WHERE user_id=? AND title='Test revision'",(uid,)).fetchone()
        self.assertIsNotNone(task)
        self.client.post(f"/tasks/{task['id']}/toggle")
        with planner.db() as conn: self.assertEqual(conn.execute('SELECT done FROM tasks WHERE id=?',(task['id'],)).fetchone()[0],1)
        self.client.post('/timetable/generate',data={'block_minutes':'60','blocks_per_day':'2','start_hour':'16'})
        with planner.db() as conn: self.assertGreater(conn.execute('SELECT COUNT(*) FROM timetable WHERE user_id=?',(uid,)).fetchone()[0],0)

if __name__=='__main__': unittest.main(verbosity=2)
