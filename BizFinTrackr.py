from flask import Flask, render_template, redirect, url_for, flash, request, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, and_, or_, Date, cast
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import random
import string
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "postgresql://localhost/bizfintrackr")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ========================== MODELS ==========================

class Business(db.Model):
    __tablename__ = 'business'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    business_code_prefix = db.Column(db.String(100), unique=True)

    owner = db.relationship('User', foreign_keys=[owner_id], backref='owned_business', uselist=False)
    users = db.relationship('User', backref='business', foreign_keys='User.business_id', lazy=True)
    products = db.relationship('Product', backref='business', lazy=True)
    sales = db.relationship('Sale', backref='business', lazy=True)
    expenses = db.relationship('Expense', backref='business', lazy=True)
    inventory_logs = db.relationship('Inventory', backref='business', lazy=True)


class User(db.Model):
    __tablename__ = 'users'  # Avoid reserved 'user' keyword

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(10), nullable=False)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=True)

    __table_args__ = (
        db.UniqueConstraint('username', 'business_id', name='_username_business_uc'),
    )

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

    sales = db.relationship('Sale', backref='product', lazy=True)
    inventory_logs = db.relationship('Inventory', backref='product', lazy=True)

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

    staff_user = db.relationship('User', foreign_keys=[staff_id])


class Expense(db.Model):
    __tablename__ = 'expense'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100))
    description = db.Column(db.Text)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    staff_user = db.relationship('User', foreign_keys=[staff_id])


class Inventory(db.Model):
    __tablename__ = 'inventory'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    staff_user = db.relationship('User', foreign_keys=[staff_id])


# Utility functions
def generate_custom_id(prefix, length=6):
    suffix = ''.join(random.choices(string.digits, k=length))
    return f"{prefix.upper()}{suffix}"

@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}
@app.route('/')
def home():
    return redirect(url_for('landing'))


@app.route('/landing')
def landing():
    return render_template('landing.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip().lower()
        password = request.form['password']
        business_name = request.form['business_name'].strip()

        if not username or not email or not password or not business_name:
            flash("All fields are required.", "danger")
            return redirect(url_for('register'))

        existing_owner_email = User.query.filter(
            func.lower(User.email) == email,
            User.role == 'owner'
        ).first()

        if existing_owner_email:
            flash('An owner account already exists with this email.', 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)

        business_code_prefix = ''.join(random.choices(string.ascii_uppercase, k=3))

        user = User(username=username, email=email, password_hash=hashed_password, role='owner')
        db.session.add(user)
        db.session.flush()

        business = Business(name=business_name, owner_id=user.id, business_code_prefix=business_code_prefix)
        db.session.add(business)
        db.session.flush()

        user.business_id = business.id
        db.session.commit()

        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = user.role
        session['business_id'] = business.id
        session['business_name'] = business.name

        flash('Registration successful! Welcome to BizFinTrackr.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']

        user = User.query.filter(func.lower(User.email) == email).first()

        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            session['business_id'] = user.business_id
            business = Business.query.get(user.business_id)
            session['business_name'] = business.name if business else "Your Business"
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('landing'))


@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        flash('Please login first.', 'warning')
        return redirect(url_for('login'))

    user_id = session['user_id']
    user_role = session['role']
    business_id = session['business_id']
    user = User.query.get(user_id)

    start_date_form = request.form.get('start_date')
    end_date_form = request.form.get('end_date')

    try:
        start_date = datetime.strptime(start_date_form, '%Y-%m-%d') if start_date_form else datetime.now() - timedelta(days=30)
        end_date = datetime.strptime(end_date_form, '%Y-%m-%d') if end_date_form else datetime.now()
    except Exception:
        start_date = datetime.now() - timedelta(days=30)
        end_date = datetime.now()

    sales = Sale.query.filter(
        Sale.business_id == business_id,
        Sale.date >= start_date,
        Sale.date <= end_date
    ).all()

    expenses = Expense.query.filter(
        Expense.business_id == business_id,
        Expense.date >= start_date,
        Expense.date <= end_date
    ).all()

    products = Product.query.filter_by(business_id=business_id).all()

    product_summary = []
    for product in products:
        product_summary.append({
            'product': product,
            'in_stock': product.in_stock,
            'total_sold': product.total_sold
        })

    total_revenue = sum(s.total_amount for s in sales)
    total_expenses = sum(e.amount for e in expenses)
    net_profit = total_revenue - total_expenses
    net_profit_percentage = (net_profit / total_revenue) * 100 if total_revenue else 0

    today = datetime.now().date()
    daily_sales = Sale.query.filter(
        Sale.business_id == business_id,
        cast(Sale.date, Date) == today
    ).all()
    total_daily_sales_count = sum(s.quantity for s in daily_sales)

    recent_sales = []
    for s in sales[-5:][::-1]:
        recent_sales.append({
            'product': s.product,
            'quantity_sold': s.quantity,
            'sale_price': s.total_amount / s.quantity if s.quantity > 0 else 0,
            'sale_date': s.date,
            'staff_user': s.staff_user,
            'custom_id': s.product.custom_id if s.product else None
        })

    return render_template('dashboard.html',
                           user=user,
                           user_role=user_role,
                           products=product_summary,
                           sales=recent_sales,
                           expenses=expenses[-5:][::-1],
                           total_revenue=total_revenue,
                           total_expenses=total_expenses,
                           net_profit=net_profit,
                           net_profit_percentage=net_profit_percentage,
                           total_daily_sales_count=total_daily_sales_count,
                           start_date_form=start_date.strftime('%Y-%m-%d'),
                           end_date_form=end_date.strftime('%Y-%m-%d'))
@app.route('/products')
def products():
    if 'user_id' not in session:
        flash('Please login first.', 'warning')
        return redirect(url_for('login'))

    business_id = session['business_id']
    products = Product.query.filter_by(business_id=business_id).all()

    product_summary = []
    for product in products:
        product_summary.append({
            'product': product,
            'in_stock': product.in_stock,
            'total_sold': product.total_sold
        })

    return render_template('products.html', products=product_summary)


@app.route('/add_product', methods=['GET', 'POST'])
def add_product():
    if 'user_id' not in session:
        flash('Please login first.', 'warning')
        return redirect(url_for('login'))

    business_id = session['business_id']

    if request.method == 'POST':
        name = request.form['name'].strip()
        price = float(request.form['price'])
        cost = float(request.form['cost'])

        existing_product = Product.query.filter_by(name=name, business_id=business_id).first()
        if existing_product:
            flash('Product already exists.', 'danger')
            return redirect(url_for('add_product'))

        business = Business.query.get(business_id)
        if not business:
            flash('Business not found.', 'danger')
            return redirect(url_for('dashboard'))

        custom_id = f"{business.business_code_prefix}-{''.join(random.choices(string.digits, k=5))}"
        new_product = Product(name=name, price=price, cost=cost, business_id=business_id, custom_id=custom_id)
        db.session.add(new_product)
        db.session.commit()

        flash('Product added successfully!', 'success')
        return redirect(url_for('products'))

    return render_template('add_product.html')


@app.route('/restock/<int:product_id>', methods=['GET', 'POST'])
def restock_product(product_id):
    if 'user_id' not in session:
        flash('Please login first.', 'warning')
        return redirect(url_for('login'))

    product = Product.query.get_or_404(product_id)

    if product.business_id != session['business_id']:
        flash("You are not authorized to access this product.", "danger")
        return redirect(url_for('products'))

    if request.method == 'POST':
        quantity = int(request.form['quantity'])
        if quantity <= 0:
            flash('Quantity must be positive.', 'danger')
            return redirect(url_for('restock_product', product_id=product_id))

        product.in_stock += quantity

        inventory = Inventory(
            quantity=quantity,
            product_id=product.id,
            staff_id=session['user_id']
        )
        db.session.add(inventory)
        db.session.commit()

        flash('Product restocked successfully.', 'success')
        return redirect(url_for('products'))

    return render_template('restock_product.html', product=product)


@app.route('/sell/<int:product_id>', methods=['GET', 'POST'])
def sell_product(product_id):
    if 'user_id' not in session:
        flash('Please login first.', 'warning')
        return redirect(url_for('login'))

    product = Product.query.get_or_404(product_id)

    if product.business_id != session['business_id']:
        flash("You are not authorized to sell this product.", "danger")
        return redirect(url_for('products'))

    if request.method == 'POST':
        quantity = int(request.form['quantity'])

        if quantity <= 0 or quantity > product.in_stock:
            flash('Invalid quantity.', 'danger')
            return redirect(url_for('sell_product', product_id=product_id))

        product.in_stock -= quantity
        product.total_sold += quantity

        sale = Sale(
            quantity=quantity,
            total_amount=quantity * product.price,
            product_id=product.id,
            business_id=session['business_id'],
            staff_id=session['user_id']
        )
        db.session.add(sale)
        db.session.commit()

        flash('Sale recorded successfully.', 'success')
        return redirect(url_for('products'))

    return render_template('sell_product.html', product=product)


@app.route('/record_sale')
def record_sale():
    flash('Please use the "Sell" button for each product to record a sale.', 'info')
    return redirect(url_for('products'))


@app.route('/sales')
def sales():
    if 'user_id' not in session:
        flash('Please login first.', 'warning')
        return redirect(url_for('login'))

    business_id = session['business_id']
    sales = Sale.query.filter_by(business_id=business_id).order_by(Sale.date.desc()).all()
    return render_template('sales.html', sales=sales)


@app.route('/expenses')
def expenses():
    if 'user_id' not in session:
        flash('Please login first.', 'warning')
        return redirect(url_for('login'))

    business_id = session['business_id']
    expenses = Expense.query.filter_by(business_id=business_id).order_by(Expense.date.desc()).all()
    return render_template('expenses.html', expenses=expenses)


@app.route('/add_expense', methods=['GET', 'POST'])
def add_expense():
    if 'user_id' not in session:
        flash('Please login first.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        amount = float(request.form['amount'])
        category = request.form['category'].strip()
        description = request.form['description'].strip()

        if amount <= 0:
            flash("Amount must be greater than zero.", "danger")
            return redirect(url_for('add_expense'))

        expense = Expense(
            amount=amount,
            category=category,
            description=description,
            business_id=session['business_id'],
            staff_id=session['user_id']
        )
        db.session.add(expense)
        db.session.commit()

        flash("Expense recorded successfully.", "success")
        return redirect(url_for('expenses'))

    return render_template('add_expense.html')


@app.route('/profile')
def profile():
    if 'user_id' not in session:
        flash('Please login first.', 'warning')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    return render_template('profile.html', user=user)


@app.route('/add_staff', methods=['GET', 'POST'])
def add_staff():
    if session.get('role') != 'owner':
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip().lower()
        password = request.form['password']

        if not username or not email or not password:
            flash('All fields are required.', 'danger')
            return redirect(url_for('add_staff'))

        existing_user = User.query.filter(func.lower(User.email) == email).first()
        if existing_user:
            flash('Email is already in use.', 'danger')
            return redirect(url_for('add_staff'))

        hashed_password = generate_password_hash(password)
        staff = User(
            username=username,
            email=email,
            password_hash=hashed_password,
            role='staff',
            business_id=session['business_id']
        )
        db.session.add(staff)
        db.session.commit()

        flash('Staff account created successfully.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('add_staff.html')


@app.route('/reports')
def reports():
    if session.get('role') != 'owner':
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))

    # Placeholder logic
    flash("Reports section coming soon.", "info")
    return redirect(url_for('dashboard'))


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
