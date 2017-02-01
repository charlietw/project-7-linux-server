from flask import Flask, render_template, request, \
  redirect, jsonify, url_for, flash
from sqlalchemy import create_engine, asc
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Supplier, Meal, User
from flask import session as login_session
import random
import string
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests
from functools import wraps
from flask.ext.sqlalchemy import SQLAlchemy


app = Flask(__name__)
app.config.from_pyfile('config.py')
db = SQLAlchemy(app)

CLIENT_ID = json.loads(
   open('/var/www/catalog/catalog/client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "Restaurant Menu Application"

engine = create_engine("postgresql://catalog:udac1ty!@127.0.0.1/catalog")
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()

@app.route('/login')
def showLogin():
    """Create anti-forgery state token"""
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    login_session['state'] = state
    return render_template('login.html', STATE=state)


@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('/var/www/catalog/catalog/client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_credentials = login_session.get('credentials')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_credentials is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps('User is already connected.'),
                                 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['credentials'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    # See if user exists, if it doesn't, make a new one.

    try:
        user_id = getUserID(login_session['email'])
        if not user_id:
            createUser(login_session)
        login_session['user_id'] = user_id
        print user_id
        print login_session['user_id']
    except:
        print "Error"

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    flash("You are now logged in as %s." % login_session['username'])
    print "done!"
    return output


def createUser(login_session):
    newUser = User(name=login_session['username'], email=login_session[
                    'email'], picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id


def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user


def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None


@app.route('/gdisconnect')
def gdisconnect():
    if 'username' not in login_session:
        flash("You were not logged in!")
        print "Not logged in."
        return redirect(url_for('home'))
    credentials = login_session['credentials']
    print credentials
    access_token = credentials
    print 'In gdisconnect access token is %s', access_token
    print access_token
    print 'User name is: '
    print login_session['username']
    if access_token is None:
        print 'Access Token is None'
        response = make_response(
                    json.dumps('Current user not connected.'), 401
                    )
        response.headers['Content-Type'] = 'application/json'
        return response
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    print 'result is '
    print result
    if result['status'] == '200':
        del login_session['credentials']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']
        del login_session['user_id']
        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        print response
        flash("Successfully logged out.")
        return redirect(url_for('home'))
    else:
        response = make_response(
            json.dumps('Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response


# JSON APIs to view supplier Information
@app.route('/supplier/<int:supplier_id>/meals/JSON')
def supplierMenuJSON(supplier_id):
    supplier = session.query(Supplier).filter_by(id=supplier_id).one()
    items = session.query(Meal).filter_by(supplier_id=supplier_id).all()
    return jsonify(Meals=[i.serialize for i in items])


@app.route('/supplier/<int:supplier_id>/meals/<int:meal_id>/JSON')
def mealJSON(supplier_id, meal_id):
    meal = session.query(Meal).filter_by(id=meal_id).one()
    return jsonify(Meal=meal.serialize)


@app.route('/meals/JSON')
def mealsJSON():
    meals = session.query(Meal).all()
    return jsonify(Meals=[r.serialize for r in meals])


@app.route('/suppliers/JSON')
def suppliersJSON():
    suppliers = session.query(Supplier).all()
    return jsonify(Suppliers=[r.serialize for r in suppliers])


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' in login_session:
            return f(*args, **kwargs)
        else:
            flash("You must log in to access this page.")
            return redirect('/login')
    return decorated_function


def check_author(object):
    try:
        if object.user.name == login_session['username']:
            return True
        else:
            flash("You do not have permission to modify this record.")
    except:
        # I have put this in because I added
        # the 'user' attribute to the 'Meal' class
        # late, so not every record has a 'user'.
        if not object.user:
            return True
        else:
            flash("An error ocurred (refer to the check_author function).")


@app.route('/')
@app.route('/home/')
def home():
    suppliers = session.query(Supplier).order_by(asc(Supplier.name))
    return render_template('home.html', suppliers=suppliers)


@app.route('/suppliers')
def suppliers():
    suppliers = session.query(Supplier).order_by(asc(Supplier.name))
    print login_session
    return render_template('suppliers.html', suppliers=suppliers)


@app.route('/supplier/new/', methods=['GET', 'POST'])
@login_required
def newSupplier():
    """Create a new supplier"""
    if request.method == 'POST':
        newSupplier = Supplier(name=request.form['name'],
                               user_id=login_session['user_id'])
        session.add(newSupplier)
        flash('New Supplier %s successfully created' % newSupplier.name)
        session.commit()
        return redirect(url_for('home'))
    else:
        return render_template('newSupplier.html')


@app.route('/supplier/<int:supplier_id>/edit/', methods=['GET', 'POST'])
@login_required
def editSupplier(supplier_id):
    """Edit a supplier"""
    editedSupplier = session.query(Supplier).filter_by(id=supplier_id).one()
    if request.method == 'POST':
        if request.form['name'] and check_author(editedSupplier) is True:
            editedSupplier.name = request.form['name']
            session.commit()
            flash('Successfully renamed supplier to %s' % editedSupplier.name)
            return redirect(url_for('suppliers'))
    return render_template('editSupplier.html', supplier=editedSupplier)


@app.route('/supplier/<int:supplier_id>/')
@app.route('/supplier/<int:supplier_id>/menu/')
def showMenu(supplier_id):
    """Show the menu of one particular supplier"""
    supplier = session.query(Supplier).filter_by(id=supplier_id).one()
    meals = session.query(Meal).filter_by(supplier_id=supplier_id).all()
    return render_template('meals.html', meals=meals, supplier=supplier)


@app.route('/newmeal/', methods=['GET', 'POST'])
@login_required
def newMeal():
    """Create a new meal"""
    suppliers = session.query(Supplier).all()
    if request.method == 'POST':
        newMeal = Meal(name=request.form['name'],
                       description=request.form['description'],
                       price=request.form['price'],
                       supplier_id=request.form['supplier'],
                       user_id=login_session['user_id'])
        session.add(newMeal)
        session.commit()
        flash('New meal "%s" successfully created' % (newMeal.name))
        return redirect(url_for('home'))
    else:
        return render_template('newMeal.html', suppliers=suppliers)


@app.route('/supplier/<int:supplier_id>/menu/<int:meal_id>/edit',
           methods=['GET', 'POST'])
@login_required
def editmeal(supplier_id, meal_id):
    """ Edit a meal """
    editedMeal = session.query(Meal).filter_by(id=meal_id).one()
    supplier = session.query(Supplier).filter_by(id=supplier_id).one()
    if request.method == 'POST':
        if check_author(editedMeal):
            if request.form['name']:
                editedMeal.name = request.form['name']
            if request.form['description']:
                editedMeal.description = request.form['description']
            if request.form['price']:
                editedMeal.price = request.form['price']
            session.add(editedMeal)
            session.commit()
            flash('Menu Item Successfully Edited')
            return redirect(url_for('showMenu', supplier_id=supplier_id))
    return render_template('editmeal.html',
                           supplier_id=supplier_id,
                           meal_id=meal_id,
                           item=editedMeal)


@app.route('/supplier/<int:supplier_id>/menu/<int:meal_id>/delete',
           methods=['GET', 'POST'])
@login_required
def deleteMeal(supplier_id, meal_id):
    """Delete a menu item"""
    supplier = session.query(Supplier).filter_by(id=supplier_id).one()
    itemToDelete = session.query(Meal).filter_by(id=meal_id).one()
    if request.method == 'POST':
        if check_author(itemToDelete):
            session.delete(itemToDelete)
            session.commit()
            flash('Meal successfully deleted')
            return redirect(url_for('showMenu', supplier_id=supplier_id))
    return render_template('deleteMeal.html', item=itemToDelete)


if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host='0.0.0.0', port=5000)

