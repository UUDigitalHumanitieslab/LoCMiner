# LoCMiner

The LoCMiner is a simple web application that allows users to search the 
[Chronicling America collection](http://chroniclingamerica.loc.gov/) of the 
[Library of Congress](http://www.loc.gov/) and then easily export their data 
to text mining tools of their choice.

## Back-end

The LoCMiner is written in the [Flask microframework](http://flask.pocoo.org/) 
with the [SQLAlchemy extension](https://pythonhosted.org/Flask-SQLAlchemy/) for ORM. 
All requests to the Chronicling America collection are processed using the 
[Requests: HTTP for Humans](http://docs.python-requests.org/) package. 

For a local installation, the following steps should be sufficient:

    > sudo apt install postgresql

Setup a PostgreSQL database user and place the database configuration in `config.py`.

    > git clone https://github.com/UUDigitalHumanitieslab/LoCMiner.git
    > cd LoCMiner
    > pip install -r requirements.txt
    > python2 run.py
    
This will start the web interface. To process searches, you should start 
[Redis](http://redis.io/) (usually booted on start-up) and 
[Celery](http://www.celeryproject.org/) (in a separate shell):

    > celery -A LoCMiner.tasks worker
    
You can specify your settings in `LoCMiner/config.py`. 
If you want to use the *DevelopmentConfig*, be sure to change this in 
both `run.py` and `LoCMiner/factories.py`. 

The user interface should now be reachable from `http://localhost:5000`.

## Front-end

On the front-end the [PureCSS](http://purecss.io/) package is used primarily for the lay-out. 
The following JavaScript libraries are employed:

- [jQuery](http://jquery.com/)
- [DataTables](http://datatables.net/)
- [HighCharts](http://www.highcharts.com/)

## Text Mining

### Texcavator

The application allows for synergy with the text mining tool [Texcavator](https://github.com/UUDigitalHumanitieslab/texcavator). 
Your saved searches can be indexed to an [Elasticsearch](http://www.elasticsearch.org/) cluster via the 
[pyelasticsearch](http://pyelasticsearch.readthedocs.org/en/latest/) package. 
You can then freely search your results with Texcavator. 

### Voyant

The application can return a simple output file for use in the online text mining tool [Voyant](http://voyant-tools.org/). 

### Export to .csv and .txt

Finally, the application allows for simple exports of both metadata (to a .csv-file) and full-text (to .txt-files). 

## Demo

A demonstrator is available [here](https://dhtest2.hum.uu.nl/locminer). Currently access is limited to a select
number of Utrecht University students and employees. If you want a peek, contact the 
[Digital Humanities lab](http://digitalhumanities.wp.hum.uu.nl/).
