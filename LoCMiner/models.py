from datetime import datetime

from .extensions import db


class SavedSearch(db.Model):
    """A SavedSearch is a search started by a user. """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True)
    url = db.Column(db.String(200))
    task_id = db.Column(db.String(200))
    task_status = db.Column(db.String(200))

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return '<SavedSearch %r>' % self.name


class Result(db.Model):
    """A Result is a result line of a SavedSearch. """
    id = db.Column(db.Integer, primary_key=True)
    saved_search_id = db.Column(db.Integer, db.ForeignKey('saved_search.id'))
    saved_search = db.relationship('SavedSearch', foreign_keys='Result.saved_search_id',
                                   backref=db.backref('results', lazy='dynamic'))
    lccn = db.Column(db.String(200))
    date = db.Column(db.Date())
    newspaper = db.Column(db.String(200))
    place = db.Column(db.String(200))
    state = db.Column(db.String(200))
    publisher = db.Column(db.String(200))
    language = db.Column(db.String(200))
    frequency = db.Column(db.String(200))
    ocr = db.Column(db.Text)

    def __init__(self, saved_search_id, result):
        self.saved_search_id = saved_search_id
        self.lccn = result['id']
        self.date = self.as_date(result['date'])
        self.newspaper = result['title']
        self.place = self.as_list(result['county'])
        self.state = self.as_list(result['state'])
        self.publisher = result['publisher']
        self.language = self.as_list(result['language'])
        self.frequency = result['frequency']
        self.ocr = result['ocr_eng']

    def __repr__(self):
        return '<Result %r>' % self.id

    def __str__(self):
        return 'Result (%s)' % self.lccn

    @property
    def serialize(self):
        """Returns a Result in a serializable format"""
        return {
            'paper_dc_date': self.date.strftime('%Y-%m-%d'),
            'paper_dc_title': self.newspaper,
            'paper_dcterms_spatial': (self.place if self.place else 'unknown'),
            'paper_dcterms_temporal': self.frequency,
            'article_dc_title': self.newspaper,
            'article_dc_subject': 'newspaper',
            'text_content': self.ocr,
            'identifier': self.lccn
        }

    @staticmethod
    def as_date(d):
        """Converts a LOC date to a Python datetime object. """
        try:
            result = datetime.strptime(d, '%Y%m%d')
        except ValueError:
            # print '%s-%s-%s' % (d[:4], d[4:6], d[6:])
            result = None
        return result

    @staticmethod
    def as_list(l):
        """Converts a LOC list to a string separated by commas. """
        if any(v is None for v in l):
            return None
        else:
            return ','.join(l)