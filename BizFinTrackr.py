import os
import random
import string
from datetime import datetime
from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func
import logging

# Logging setup
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://username:password@localhost/yourdb')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# MODELS
class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(10), nullable=False)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=True)

    business = db.relationship("Business", back_populates="users")

    __table_args__ = (
        db.UniqueConstraint('username', 'business_id', name='_username_business_uc'),
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Business(db.Model):
    __tablename__ = 'business'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    business_code_prefix = db.Column(db.String(100), unique=True)

    owner = db.relationship("User", foreign_keys=[owner_id], backref="owned_business")
    users = db.relationship("User", back_populates="business", foreign_keys=[User.business_id])

    products = db.relationship("Product", back_populates="business", cascade="all, delete-orphan")
    sales = db.relationship("Sale", back_populates="business", cascade="all, delete-orphan")
    expenses = db.relationship("Expense", back_populates="business", cascade="all, delete-orphan")


class Product(db.Model):
    __tablename__ = 'product'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    cost = db.Column(db.Float, nullable=False)
    in_stock = db.Column(db.Integer, nullable=False, default=0)
    total_sold = db.Column(db.Integer, nullable=False, default=0)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    custom_id = db.Column(db.String(50), unique=True)

    business = db.relationship("Business", back_populates="products")
    sales = db.relationship("Sale", back_populates="product", cascade="all, delete-orphan")
    inventory_logs = db.relationship("Inventory", back_populates="product", cascade="all, delete-orphan")

    __table_args__ = (
        db.UniqueConstraint('name', 'business_id', name='_name_business_uc'),
    )


class Sale(db.Model):
    __tablename__ = 'sale'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)

    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    product = db.relationship("Product", back_populates="sales")
    business = db.relationship("Business", back_populates="sales")
    staff = db.relationship("User", foreign_keys=[staff_id])


class Expense(db.Model):
    __tablename__ = 'expense'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100))
    description = db.Column(db.Text)

    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    business = db.relationship("Business", back_populates="expenses")
    staff = db.relationship("User", foreign_keys=[staff_id])


class Inventory(db.Model):
    __tablename__ = 'inventory'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    product = db.relationship("Product", back_populates="inventory_logs")
    staff = db.relationship("User", foreign_keys=[staff_id])
# ----------------------------------
# DATABASE MODELS
# ----------------------------------

class Business(db.Model):
    __tablename__ = 'business'
    __table_args__ = {'extend_existing': True}  # ✅ This line resolves the error
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    business_code_prefix = db.Column(db.String(100), unique=True)
    
    users = db.relationship('User', backref='business', foreign_keys='User.business_id')
    products = db.relationship('Product', backref='business', lazy=True)
    sales = db.relationship('Sale', backref='business', lazy=True)
    expenses = db.relationship('Expense', backref='business', lazy=True)

class User(db.Model):
    __tablename__ = 'users'  # Avoid reserved word "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(10), nullable=False)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=True)

    __table_args__ = (db.UniqueConstraint('username', 'business_id', name='_username_business_uc'),)

    sales = db.relationship('Sale', backref='staff', foreign_keys='Sale.staff_id', lazy=True)
    expenses = db.relationship('Expense', backref='staff', foreign_keys='Expense.staff_id', lazy=True)
    inventories = db.relationship('Inventory', backref='staff', foreign_keys='Inventory.staff_id', lazy=True)

class Product(db.Model):
    __tablename__ = 'product'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    cost = db.Column(db.Float, nullable=False)
    in_stock = db.Column(db.Integer, nullable=False, default=0)
    total_sold = db.Column(db.Integer, nullable=False, default=0)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    custom_id = db.Column(db.String(50), unique=True)

    __table_args__ = (db.UniqueConstraint('name', 'business_id', name='_name_business_uc'),)

    sales = db.relationship('Sale', backref='product', lazy=True)
    inventories = db.relationship('Inventory', backref='product', lazy=True)

class Sale(db.Model):
    __tablename__ = 'sale'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    quantity = db.Column(db.Integer, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('users.id'))

class Expense(db.Model):
    __tablename__ = 'expense'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100))
    description = db.Column(db.Text)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('users.id'))

class Inventory(db.Model):
    __tablename__ = 'inventory'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    quantity = db.Column(db.Integer, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('users.id'))

# ----------------------------------
# UTILITY FUNCTIONS
# ----------------------------------

def generate_business_code(name):
    prefix = ''.join(filter(str.isalnum, name.lower()))[:4]
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return prefix.upper() + '-' + suffix

# ----------------------------------
# ROUTES
# ----------------------------------

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('landing'))

@app.route('/landing')
def landing():
    return render_template('landing.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        business_name = request.form['business_name']

        if not username or not email or not password or not business_name:
            flash('All fields are required.')
            return redirect(url_for('register'))

        existing_owner_email = User.query.filter(
            func.lower(User.email) == func.lower(email),
            User.role == 'owner'
        ).first()

        if existing_owner_email:
            flash('An owner with that email already exists.')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)

        # Create new business and owner
        new_user = User(username=username, email=email, password_hash=hashed_password, role='owner')
        db.session.add(new_user)
        db.session.flush()  # Get new_user.id before commit

        business_code = generate_business_code(business_name)
        new_business = Business(name=business_name, owner_id=new_user.id, business_code_prefix=business_code)
        db.session.add(new_business)
        db.session.flush()  # Get new_business.id before commit

        new_user.business_id = new_business.id

        db.session.commit()

        session['user_id'] = new_user.id
        session['role'] = new_user.role

        flash('Registration successful.')
        return redirect(url_for('dashboard'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter(func.lower(User.email) == func.lower(email)).first()

        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['role'] = user.role
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    business = Business.query.get(user.business_id)

    total_products = Product.query.filter_by(business_id=business.id).count()
    total_sales = db.session.query(func.sum(Sale.total_amount)).filter_by(business_id=business.id).scalar() or 0
    total_expenses = db.session.query(func.sum(Expense.amount)).filter_by(business_id=business.id).scalar() or 0
    net_profit = total_sales - total_expenses

    return render_template('dashboard.html',
                           user=user,
                           business=business,
                           total_products=total_products,
                           total_sales=total_sales,
                           total_expenses=total_expenses,
                           net_profit=net_profit)

# --------------------------
# PRODUCT MANAGEMENT
# --------------------------

@app.route('/products')
def products():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    product_list = Product.query.filter_by(business_id=user.business_id).all()
    return render_template('products.html', products=product_list, user=user)

@app.route('/add_product', methods=['POST'])
def add_product():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    name = request.form['name']
    price = float(request.form['price'])
    cost = float(request.form['cost'])

    # Prevent duplicate product names for same business
    existing = Product.query.filter_by(name=name, business_id=user.business_id).first()
    if existing:
        flash('Product with this name already exists.')
        return redirect(url_for('products'))

    custom_id = generate_business_code(name)

    new_product = Product(name=name, price=price, cost=cost, business_id=user.business_id, custom_id=custom_id)
    db.session.add(new_product)
    db.session.commit()

    flash('Product added successfully.')
    return redirect(url_for('products'))

@app.route('/update_product/<int:product_id>', methods=['POST'])
def update_product(product_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    product = Product.query.get_or_404(product_id)
    name = request.form['name']
    price = float(request.form['price'])
    cost = float(request.form['cost'])

    # Ensure no duplicate name for same business
    existing = Product.query.filter(
        Product.name == name,
        Product.business_id == product.business_id,
        Product.id != product.id
    ).first()
    if existing:
        flash('Another product with this name already exists.')
        return redirect(url_for('products'))

    product.name = name
    product.price = price
    product.cost = cost
    db.session.commit()

    flash('Product updated successfully.')
    return redirect(url_for('products'))

@app.route('/delete_product/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted successfully.')
    return redirect(url_for('products'))

# --------------------------
# SALES
# --------------------------

@app.route('/sales')
def sales():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    sales_list = Sale.query.filter_by(business_id=user.business_id).order_by(Sale.date.desc()).all()
    return render_template('sales.html', sales=sales_list, user=user)

@app.route('/record_sale', methods=['POST'])
def record_sale():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    product_id = int(request.form['product_id'])
    quantity = int(request.form['quantity'])

    product = Product.query.get_or_404(product_id)

    if product.in_stock < quantity:
        flash('Insufficient stock.')
        return redirect(url_for('sales'))

    total_amount = quantity * product.price

    sale = Sale(
        product_id=product_id,
        quantity=quantity,
        total_amount=total_amount,
        business_id=user.business_id,
        staff_id=user.id
    )

    product.in_stock -= quantity
    product.total_sold += quantity

    db.session.add(sale)
    db.session.commit()

    flash('Sale recorded successfully.')
    return redirect(url_for('sales'))

# --------------------------
# EXPENSES
# --------------------------

@app.route('/expenses')
def expenses():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    expense_list = Expense.query.filter_by(business_id=user.business_id).order_by(Expense.date.desc()).all()
    return render_template('expenses.html', expenses=expense_list, user=user)

@app.route('/add_expense', methods=['POST'])
def add_expense():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    amount = float(request.form['amount'])
    category = request.form['category']
    description = request.form['description']

    expense = Expense(
        amount=amount,
        category=category,
        description=description,
        business_id=user.business_id,
        staff_id=user.id
    )

    db.session.add(expense)
    db.session.commit()

    flash('Expense recorded successfully.')
    return redirect(url_for('expenses'))

# --------------------------
# INVENTORY
# --------------------------

@app.route('/inventory')
def inventory():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    inventory_list = Inventory.query.join(Product).filter(
        Inventory.product_id == Product.id,
        Product.business_id == user.business_id
    ).order_by(Inventory.date.desc()).all()

    product_list = Product.query.filter_by(business_id=user.business_id).all()
    return render_template('inventory.html', inventory=inventory_list, products=product_list, user=user)

@app.route('/add_inventory', methods=['POST'])
def add_inventory():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    product_id = int(request.form['product_id'])
    quantity = int(request.form['quantity'])

    product = Product.query.get_or_404(product_id)
    product.in_stock += quantity

    inventory = Inventory(
        product_id=product_id,
        quantity=quantity,
        staff_id=user.id
    )

    db.session.add(inventory)
    db.session.commit()

    flash('Stock updated successfully.')
    return redirect(url_for('inventory'))

# --------------------------
# JSON API (Optional)
# --------------------------

@app.route('/api/products')
def api_products():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user = User.query.get(session['user_id'])
    products = Product.query.filter_by(business_id=user.business_id).all()

    return jsonify([{
        'id': p.id,
        'name': p.name,
        'price': p.price,
        'cost': p.cost,
        'in_stock': p.in_stock,
        'total_sold': p.total_sold,
        'custom_id': p.custom_id
    } for p in products])

# --------------------------
# ERROR HANDLERS
# --------------------------

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template('500.html'), 500

# --------------------------
# RUN APP
# --------------------------

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
