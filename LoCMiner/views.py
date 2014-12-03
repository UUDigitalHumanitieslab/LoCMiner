from flask import Blueprint, request, render_template, \
    redirect, url_for, make_response, flash, Response, jsonify
from pyelasticsearch import ElasticSearch
from collections import Counter, defaultdict
from celery.result import AsyncResult
from math import ceil
import requests
import StringIO
import csv
import zipfile

from .factories import db
from .models import SavedSearch, Result

site = Blueprint('site', __name__)

# LoC Settings
BASE_URL = 'http://chroniclingamerica.loc.gov'
SEARCH_URL = '/search/pages/results/'
MAX_RESULTS = 1000
MIN_CORPUS_DATE = 1836
MAX_CORPUS_DATE = 1922
# ElasticSearch settings
ES_CLUSTER = 'http://localhost:9200/'
ES_INDEX = 'kb'
ES_TYPE = 'doc'
es = ElasticSearch(ES_CLUSTER)


@site.route('/')
def home():
    """Renders the home view. """
    return render_template('home.html')


@site.route('/search/', methods=['GET', 'POST'])
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
            return render_template('search.html',
                                   date_from=MIN_CORPUS_DATE,
                                   date_to=MAX_CORPUS_DATE,
                                   f=request.form)

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
            return redirect(url_for('.show_results', search_id=saved_search.id))
        else:
            return render_template('search.html',
                                   date_from=MIN_CORPUS_DATE,
                                   date_to=MAX_CORPUS_DATE,
                                   f=request.form)
    else:
        return render_template('search.html',
                               date_from=MIN_CORPUS_DATE,
                               date_to=MAX_CORPUS_DATE,
                               f={})


@site.route('/searches/')
def show_searches():
    """Shows all completed SavedSearches. """
    return render_template('show_searches.html', saved_searches=SavedSearch.query.all())


@site.route('/delete/<search_id>/')
def delete_search(search_id):
    """Deletes a SavedSearch from the database. """
    ss = SavedSearch.query.filter_by(id=search_id).first_or_404()
    db.session.delete(ss)
    db.session.commit()
    flash('Search successfully deleted', 'success')
    return render_template('show_searches.html', saved_searches=SavedSearch.query.all())


@site.route('/download/<search_id>/')
def download(search_id):
    """ Returns a list of all OCR Results for a SavedSearch. """
    ss = SavedSearch.query.filter_by(id=search_id).first_or_404()
    results = ss.results.order_by(Result.date)

    texts = list()
    for r in results:
        texts.append(BASE_URL + r.lccn + 'ocr.txt')

    return make_response('<br>'.join(texts))


@site.route('/metadata/<search_id>/')
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


@site.route('/zip/<search_id>/')
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


@site.route('/chart/<search_id>/')
def chart(search_id):
    """ Returns a line chart for a SavedSearch """
    ss = SavedSearch.query.filter_by(id=search_id).first_or_404()
    results = ss.results.order_by(Result.date)

    months = defaultdict(Counter)
    for result in results:
        months[result.date.year][result.date.month] += 1

    return render_template('chart.html', saved_search=ss, months=months)


@site.route('/results/<search_id>/')
def show_results(search_id):
    """ Shows all Results for a SavedSearch. """
    ss = SavedSearch.query.filter_by(id=search_id).first_or_404()
    r = ss.results.all()
    return render_template('show_results.html', saved_search=ss, results=r, b=BASE_URL)


@site.route('/state/<search_id>/')
def state(search_id):
    """ Returns the (Celery) state of a SavedSearch. """
    ss = SavedSearch.query.filter_by(id=search_id).first_or_404()
    res = AsyncResult(ss.task_id)
    if res.status == 'PROGRESS':
        percentage = ceil(res.info['current'] / float(res.info['total']) * 100)
        return jsonify(result=percentage)
    else:
        value = 100 if res.status == 'SUCCESS' else 0
        return jsonify(result=value)


@site.route('/index/<search_id>/')
def index(search_id):
    """ Indexes the given search """
    ss = SavedSearch.query.filter_by(id=search_id).first_or_404()
    results = ss.results.all()
    for r in results:
        es.index(ES_INDEX, ES_TYPE, r.serialize)
    flash('Successfully indexed!', 'success')
    return show_results(search_id)


@site.route('/_json/<result_id>/')
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
        from .tasks import write_results
        res = write_results.delay(saved_search.id, search_term, total_items)

        saved_search.url = r.url
        saved_search.task_id = res.id

        db.session.add(saved_search)
        db.session.commit()

        return True
