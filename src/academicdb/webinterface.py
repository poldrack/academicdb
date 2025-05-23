"""
Web interface to academicdb
"""

import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from academicdb.database import Database, MongoDatabase
from academicdb.dbbuilder import main as dbbuilder_main
import argparse
import logging
import sys
import subprocess
import pandas as pd
import json
from pymongo import ASCENDING, DESCENDING
from academicdb.render_pubs import get_publication_years

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Setup templates directory
template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
app.template_folder = template_dir

# Define global variables
db = None
config_dir = os.path.join(os.path.expanduser('~'), '.academicdb')
base_dir = '.'

def setup_database():
    """Setup database connection"""
    global db
    configfile = os.path.join(config_dir, 'config.toml')
    if not os.path.exists(configfile):
        raise FileNotFoundError(
            f'You must first set up the config.toml file in {config_dir}'
        )
    
    # Load config to check for MongoDB connection string
    import toml
    config = toml.load(configfile)
    
    if config is not None and 'mongo' in config and 'CONNECT_STRING' in config['mongo']:
        logging.info('Using custom mongodb config')
        db = Database(
            MongoDatabase(
                connect_string=config['mongo']['CONNECT_STRING'],
            )
        )
    else:
        logging.info('Using default localhost database config')
        db = Database(MongoDatabase())
    return db

@app.route('/')
def index():
    """Main page showing database stats and navigation"""
    collections = db.list_collections()
    collection_stats = {}
    
    for collection in collections:
        data = db.get_collection(collection)
        if data:
            collection_stats[collection] = len(data)
        else:
            collection_stats[collection] = 0
            
    return render_template('index.html', 
                          collections=collections,
                          collection_stats=collection_stats)

@app.route('/collection/<name>')
def view_collection(name):
    """View contents of a specific collection"""
    if name not in db.list_collections():
        flash(f"Collection {name} does not exist")
        return redirect(url_for('index'))
    
    # Get collection data
    data = db.get_collection(name)
    
    # Get query parameters for filtering
    search_term = request.args.get('search', '')
    
    # Filter data if search term provided
    if search_term and data:
        filtered_data = []
        for item in data:
            # Convert all values to strings for searching
            item_str = json.dumps(item).lower()
            if search_term.lower() in item_str:
                filtered_data.append(item)
        data = filtered_data
    
    return render_template('collection.html', 
                          name=name, 
                          data=data, 
                          search_term=search_term)
                          
@app.route('/publications')
def view_publications():
    """View publications in a more readable format"""
    # Get publications data
    publications = db.get_collection('publications')
    
    if not publications:
        flash("No publications found in the database")
        return redirect(url_for('index'))
    
    # Get query parameters for filtering
    search_term = request.args.get('search', '')
    
    # Filter publications if search term provided
    if search_term:
        filtered_pubs = []
        for pub in publications:
            # Convert relevant fields to strings for searching
            search_fields = ['title', 'authors', 'journal', 'abstract', 'year', 'doi']
            search_text = ' '.join(str(pub.get(field, '')).lower() for field in search_fields)
            if search_term.lower() in search_text:
                filtered_pubs.append(pub)
        publications = filtered_pubs
    
    # Group publications by year
    years = get_publication_years(publications)
    publications_by_year = {}
    
    for year in years:
        year_pubs = [pub for pub in publications if pub['year'] == year]
        # Sort by first author
        year_pubs.sort(key=lambda x: x.get('authors', ''))
        publications_by_year[year] = year_pubs
    
    return render_template('publication.html', 
                          years=years,
                          publications_by_year=publications_by_year,
                          search_term=search_term)

@app.route('/reload', methods=['GET', 'POST'])
def reload_database():
    """Reload the database using dbbuilder"""
    if request.method == 'POST':
        try:
            # Create arguments similar to what dbbuilder expects
            class Args:
                def __init__(self):
                    self.configdir = config_dir
                    self.basedir = base_dir
                    self.debug = False
                    self.overwrite = True if request.form.get('overwrite') else False
                    self.no_add_pubs = False if request.form.get('add_pubs') else True
                    self.no_add_info = False if request.form.get('add_info') else True
                    self.nodb = False
                    self.test = True if request.form.get('test_mode') else False
                    self.bad_ids_file = 'bad_ids.csv'
            
            # Save original arguments
            original_args = sys.argv
            
            # Call dbbuilder main function with our custom args
            from academicdb.dbbuilder import main
            args = Args()
            
            # Run in a subprocess to avoid affecting the current process
            cmd = [sys.executable, '-m', 'academicdb.dbbuilder']
            if args.overwrite:
                cmd.append('--overwrite')
            if args.test:
                cmd.append('--test')
            if not args.no_add_pubs:
                cmd.append('--no_add_pubs')
            if not args.no_add_info:
                cmd.append('--no_add_info')
            
            process = subprocess.Popen(cmd, 
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                flash("Database reloaded successfully")
            else:
                flash(f"Error reloading database: {stderr.decode()}")
            
            # Reconnect to database after reload
            setup_database()
            
            return redirect(url_for('index'))
        except Exception as e:
            flash(f"Error: {str(e)}")
            return redirect(url_for('reload_form'))
    else:
        return render_template('reload.html')

def parse_args():
    parser = argparse.ArgumentParser(description='Run the academicdb web interface')
    parser.add_argument(
        '-c',
        '--configdir',
        type=str,
        help='directory for config files',
        default=os.path.join(os.path.expanduser('~'), '.academicdb'),
    )
    parser.add_argument(
        '-b', 
        '--basedir', 
        type=str, 
        help='base directory for additional files', 
        default='.'
    )
    parser.add_argument(
        '-p',
        '--port',
        type=int,
        help='port to run the server on',
        default=5000
    )
    parser.add_argument(
        '-d',
        '--debug',
        action='store_true',
        help='run in debug mode'
    )
    return parser.parse_args()

def main():
    """Main entry point for the web interface"""
    global config_dir, base_dir
    
    args = parse_args()
    config_dir = args.configdir
    base_dir = args.basedir
    
    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )
    
    # Setup database connection
    try:
        setup_database()
    except Exception as e:
        print(f"Error setting up database: {e}")
        sys.exit(1)
    
    # Run the Flask app
    app.run(debug=args.debug, port=args.port)

if __name__ == '__main__':
    main()