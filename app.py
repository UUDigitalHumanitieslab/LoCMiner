from flask import Flask, request, render_template, redirect, url_for, make_response, flash, Response
from flask.ext.sqlalchemy import SQLAlchemy
import requests
import os
import StringIO
import csv
import zipfile
from datetime import datetime

BASE_URL = 'http://chroniclingamerica.loc.gov'
SEARCH_URL = '/search/pages/results/'
MAX_RESULTS = 5000
MIN_CORPUS_DATE = 1836
MAX_CORPUS_DATE = 1922

app = Flask(__name__)
app.config.update(dict(
    SQLALCHEMY_DATABASE_URI='sqlite:///' + os.path.join(app.root_path, 'p.db'),
    DEBUG=True,
    SECRET_KEY='development key',
))
db = SQLAlchemy(app)

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
        self.ocr = result['ocr_eng']

    def __repr__(self):
        return '<Result %r>' % self.id

    def __str__(self):
        return 'Result (%s)' % self.lccn

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
        search_name = request.form['name'].lower()

        s = SavedSearch.query.filter_by(name=search_name).first()
        if s:
            flash('Search name already in use', 'error')
            return render_template('search.html', date_from=MIN_CORPUS_DATE, date_to=MAX_CORPUS_DATE)

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
        mine(saved_search, search_term)

        return redirect(url_for('show_results', search_id=saved_search.id))
    else:
        return render_template('search.html', date_from=MIN_CORPUS_DATE, date_to=MAX_CORPUS_DATE)


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

    response = make_response('<br>'.join(texts))
    return response


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


@app.route('/results/<search_id>/')
def show_results(search_id):
    """ Shows all Results for a SavedSearch. """
    ss = SavedSearch.query.filter_by(id=search_id).first_or_404()
    r = ss.results.all()
    return render_template('show_results.html', saved_search=ss, results=r, b=BASE_URL)


def mine(saved_search, search_term):
    """ Mines the LOC given the search term, saves the Results to the SavedSearch. """
    page = 1

    r = requests.get(BASE_URL + SEARCH_URL, params=search_term)
    saved_search.url = r.url
    db.session.add(saved_search)
    json_result = r.json()
    total_items = json_result['totalItems']
    print 'Results found: %d' % (total_items)

    if total_items > MAX_RESULTS:
        print 'Sorry, too many results'
    else:
        write_result(saved_search, r)
        end_index = json_result['endIndex']

        while end_index < total_items:
            r = requests.get(BASE_URL + SEARCH_URL, params=search_term)
            print r.url

            end_index = write_result(saved_search, r)

            page += 1
            search_term['page'] = page


def write_result(s, r):
    """ Writes a single Result to the database. """
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

