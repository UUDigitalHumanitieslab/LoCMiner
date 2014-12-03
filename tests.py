import unittest
import os

from LoCMiner.factories import create_app


class AppTestCase(unittest.TestCase):
    def setUp(self):
        app = create_app(dict(
            SQLALCHEMY_DATABASE_URI='sqlite:///' + os.path.join(os.getcwd(), 'test.db'),
            SECRET_KEY='development key',
        ))
        self.app = app.test_client()
        #db.create_all()

    def tearDown(self):
        pass

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