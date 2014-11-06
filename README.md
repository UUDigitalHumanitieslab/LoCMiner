LoCMiner
========

The LoCMiner is a simple web application that allows users to search the [Chronicling America collection](http://chroniclingamerica.loc.gov/) of the [Library of Congress](http://www.loc.gov/) and then easily export their data to text mining tools of their choice.

Code
====

The LoCMiner is written in the [Flask microframework](http://flask.pocoo.org/) with the [SQLAlchemy extension](https://pythonhosted.org/Flask-SQLAlchemy/) for ORM. All requests to the Chronicling America collection are processed using the [Requests: HTTP for Humans](http://docs.python-requests.org/) package. 

For a local installation, the following steps should be sufficient:

    git clone https://github.com/UUDigitalHumanitieslab/LoCMiner.git
    cd LoCMiner
    pip install -r requirements.txt
    python app.py
    
Demo
====

(TODO) A demonstrator will soon be set up. 
