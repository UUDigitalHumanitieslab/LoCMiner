import requests
from celery import current_task

from .extensions import db
from .factories import create_celery
from .models import SavedSearch, Result

# Start with celery -A LoCMiner.tasks worker
celery = create_celery()

BASE_URL = 'http://chroniclingamerica.loc.gov'
SEARCH_URL = '/search/pages/results/'
IN_PROGRESS = 'PROGRESS'


@celery.task(name='tasks.write_results')
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
        current_task.update_state(state=IN_PROGRESS, meta={'current': end_index, 'total': total_items})
        print '[search-id:{}] Currently at page {}, total items: {}.'.format(search_id, page, total_items)
    else:
        print '[search-id:{}] Finished, saving success state.'.format(search_id)
        with celery.app.app_context():
            ss = db.session.query(SavedSearch).get(search_id)
            ss.task_status = 'SUCCESS'
            db.session.add(ss)
            db.session.commit()


def write_result(search_id, r):
    """ Writes a single Result to the database. """
    with celery.app.app_context():
        j = r.json()
        for item in j['items']:
            result = Result(search_id, item)
            db.session.add(result)
        db.session.commit()
        return j['endIndex']