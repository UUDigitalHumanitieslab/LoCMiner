from app import app, db
import unittest
import os


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.root_path, 'test.db')
        db.create_all()

    def tearDown(self):
        db.drop_all()

    def test_home(self):
        rv = self.app.get('/')
        assert 'Start' in rv.data

    def test_search(self):
        rv = self.app.get('/search/')
        assert 'Search' in rv.data

        rv = self.search('test', '1900', '1899', '', '', '')
        assert 'Second date before first date' in rv.data

        rv = self.search('europe', '', '', '', 'europe', '')
        assert 'more than the allowed maximum' in rv.data

    def search(self, name, date1, date2, ortext, andtext, phrasetext):
        return self.app.post('/search/', data=dict(
            name=name,
            date1=date1,
            date2=date2,
            ortext=ortext,
            andtext=andtext,
            phrasetext=phrasetext,
        ), follow_redirects=True)

if __name__ == '__main__':
    unittest.main()