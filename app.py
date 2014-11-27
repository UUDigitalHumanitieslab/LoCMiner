from flask import Flask, request, render_template, redirect, url_for, make_response, flash, Response, jsonify
from flask.ext.sqlalchemy import SQLAlchemy
import requests
import StringIO
import csv
import zipfile
from pyelasticsearch import ElasticSearch
from celery import Celery
from datetime import datetime
from collections import Counter, defaultdict

# ####
# Configuration
# ####

def make_celery(app):
    celery = Celery(app.import_name, broker=app.config['CELERY_BROKER_URL'])
    celery.conf.update(app.config)
    TaskBase = celery.Task
    class ContextTask(TaskBase):
        abstract = True
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)
    celery.Task = ContextTask
    return celery

# LoC Settings
BASE_URL = 'http://chroniclingamerica.loc.gov'
SEARCH_URL = '/search/pages/results/'
MAX_RESULTS = 1000
MIN_CORPUS_DATE = 1836
MAX_CORPUS_DATE = 1922
# Elasticsearch settings
ES_CLUSTER = 'http://localhost:9200/'
ES_INDEX = 'kb'
ES_TYPE = 'doc'
# App configuration
app = Flask(__name__)
app.config.update(dict(
    SQLALCHEMY_DATABASE_URI='postgresql://loc:locminer@localhost:5432/loc',
    CELERY_BROKER_URL='redis://localhost:6379',
    CELERY_RESULT_BACKEND='redis://localhost:6379',
    DEBUG=True,
    SECRET_KEY='development key',
))
db = SQLAlchemy(app)
es = ElasticSearch(ES_CLUSTER)
celery = make_celery(app)


# ####
# Models
# ####


class SavedSearch(db.Model):
    """A SavedSearch is a search started by a user. """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True)
    url = db.Column(db.String(200))

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

    def __init__(self, saved_search, result):
        self.saved_search = saved_search
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
            'article_dc_title': self.ocr[:50],
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


# ####
# Routes
# ####


@app.route('/')
def home():
    """Renders the home view. """
    return render_template('home.html')


@app.route('/search/', methods=['GET', 'POST'])
def search():
    """
    On GET: renders the search view
    On POST: validates the form data:
        - renders the search view if there are errors
        - searches the LOC and renders the result view if correct
    """
    if request.method == 'POST':
        # Start validation
        error = False
        search_name = request.form['name'].lower()
        s = SavedSearch.query.filter_by(name=search_name).first()
        if s:
            flash('Search name already in use', 'error')
            error = True

        if request.form['date1'] > request.form['date2']:
            flash('Second date before first date', 'error')
            error = True

        if not (request.form['ortext'] or request.form['andtext'] or request.form['phrasetext']):
            flash('No search term given', 'error')
            error = True

        # If there are problems, return to the search page
        if error:
            return render_template('search.html', date_from=MIN_CORPUS_DATE, date_to=MAX_CORPUS_DATE, f=request.form)

        # No errors, start mining
        saved_search = SavedSearch(search_name)
        db.session.add(saved_search)
        db.session.commit()

        search_term = dict()
        search_term['format'] = 'json'
        search_term['page'] = 1
        search_term['ortext'] = request.form['ortext']
        search_term['andtext'] = request.form['andtext']
        search_term['phrasetext'] = request.form['phrasetext']
        search_term['date1'] = request.form['date1']
        search_term['date2'] = request.form['date2']
        search_term['dateFilterType'] = 'yearRange'

        mined = mine(saved_search, search_term)
        if mined:
            return redirect(url_for('show_results', search_id=saved_search.id))
        else:
            return render_template('search.html', date_from=MIN_CORPUS_DATE, date_to=MAX_CORPUS_DATE, f=request.form)
    else:
        return render_template('search.html', date_from=MIN_CORPUS_DATE, date_to=MAX_CORPUS_DATE, f={})


@app.route('/searches/')
def show_searches():
    """Shows all completed SavedSearches. """
    return render_template('show_searches.html', saved_searches=SavedSearch.query.all())


@app.route('/delete/<search_id>/')
def delete_search(search_id):
    """Deletes a SavedSearch from the database. """
    ss = SavedSearch.query.filter_by(id=search_id).first_or_404()
    db.session.delete(ss)
    db.session.commit()
    flash('Search successfully deleted', 'success')
    return render_template('show_searches.html', saved_searches=SavedSearch.query.all())


@app.route('/download/<search_id>/')
def download(search_id):
    """ Returns a list of all OCR Results for a SavedSearch. """
    ss = SavedSearch.query.filter_by(id=search_id).first_or_404()
    results = ss.results.order_by(Result.date)

    texts = list()
    for r in results:
        texts.append(BASE_URL + r.lccn + 'ocr.txt')

    return make_response('<br>'.join(texts))


@app.route('/metadata/<search_id>/')
def metadata(search_id):
    """ Returns a .csv-file of all Results Metadata for a SavedSearch """
    ss = SavedSearch.query.filter_by(id=search_id).first_or_404()
    results = ss.results.order_by(Result.date)

    def generate():
        for n, result in enumerate(results):
            output = StringIO.StringIO()
            writer = csv.writer(output, dialect='excel', delimiter=';', quoting=csv.QUOTE_MINIMAL)
            if n == 0:
                header = ['lccn', 'Date', 'Newspaper', 'Place',
                          'State', 'Publisher', 'Language']
                writer.writerow(header)
            row = [result.lccn, result.date, result.newspaper, result.place,
                   result.state, result.publisher, result.language]
            writer.writerow(row)
            yield output.getvalue()

    return Response(generate(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment;filename=metadata.csv'})


@app.route('/zip/<search_id>/')
def to_zip(search_id):
    """ Returns a .zip-file of all OCR Results for a SavedSearch """
    ss = SavedSearch.query.filter_by(id=search_id).first_or_404()
    results = ss.results.order_by(Result.date)

    output = StringIO.StringIO()
    zf = zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED)
    for result in results:
        text = StringIO.StringIO()
        text.write(result.ocr.encode('utf-8'))
        zf.writestr(result.lccn[1:-1].replace('/', '|') + '.txt', text.getvalue())
    zf.close()

    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = 'attachment;filename=results.zip'
    return response


@app.route('/chart/<search_id>/')
def chart(search_id):
    """ Returns a line chart for a SavedSearch """
    ss = SavedSearch.query.filter_by(id=search_id).first_or_404()
    results = ss.results.order_by(Result.date)

    months = defaultdict(Counter)
    for result in results:
        months[result.date.year][result.date.month] += 1

    return render_template('chart.html', saved_search=ss, months=months)


@app.route('/results/<search_id>/')
def show_results(search_id):
    """ Shows all Results for a SavedSearch. """
    ss = SavedSearch.query.filter_by(id=search_id).first_or_404()
    r = ss.results.all()
    return render_template('show_results.html', saved_search=ss, results=r, b=BASE_URL)


@app.route('/index/<search_id>/')
def index(search_id):
    """ Indexes the given search """
    ss = SavedSearch.query.filter_by(id=search_id).first_or_404()
    results = ss.results.all()
    for r in results:
        es.index(ES_INDEX, ES_TYPE, r.serialize)
    flash('Successfully indexed!', 'success')
    return show_results(search_id)


@app.route('/_json/<result_id>/')
def json_result(result_id):
    """ Returns a Result in JSON format. """
    result = Result.query.filter_by(id=result_id).first_or_404()
    return jsonify(result.serialize)


# ####
# Helpers
# ####

def mine(saved_search, search_term):
    """ Mines the LOC given the search term, saves the Results to the SavedSearch. """
    r = requests.get(BASE_URL + SEARCH_URL, params=search_term)
    saved_search.url = r.url
    db.session.add(saved_search)
    db.session.commit()

    j = r.json()
    total_items = j['totalItems']
    # print 'Results found: %d' % total_items

    if total_items > MAX_RESULTS:
        flash('Sorry, your search yielded {:,} results, which is more than the allowed maximum of {:,} results.'
              .format(total_items, MAX_RESULTS), 'error')
        db.session.delete(saved_search)
        db.session.commit()
        return False
    elif total_items == 0:
        flash('Sorry, your search yielded no results.', 'error')
        db.session.delete(saved_search)
        db.session.commit()
        return False
    else:
        # Retrieve the results as a background task
        res = write_results.delay(saved_search.id, search_term, total_items)
        print res.id
        return True


@celery.task(name='tasks.write')
def write_results(search_id, search_term, total_items):
    """ Writes all Results to the database. """
    r = requests.get(BASE_URL + SEARCH_URL, params=search_term)
    end_index = write_result(search_id, r)

    page = 1
    while end_index < total_items:
        page += 1
        search_term['page'] = page
        r = requests.get(BASE_URL + SEARCH_URL, params=search_term)
        end_index = write_result(search_id, r)


def write_result(search_id, r):
    """ Writes a single Result to the database. """
    s = SavedSearch.query.filter_by(id=search_id).first_or_404()
    j = r.json()
    for item in j['items']:
        result = Result(s, item)
        db.session.add(result)
    db.session.commit()
    return j['endIndex']

# ####
# Main
# ####

if __name__ == '__main__':
    app.run()
