import os
import logging
import datetime
import socket
import psycopg2  # type: ignore

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from sqlalchemy import func, and_
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# --- Configuration ---
db_url = os.environ.get('DATABASE_URL')

if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres.tsyalxhkmmvindwxzrhc:MrWhizDeveloper321@aws-0-eu-west-1.pooler.supabase.com:6543/postgres'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'a_very_secret_and_long_random_key_for_biztrack_pro_v6_main_screens' # IMPORTANT: CHANGE THIS IN PRODUCTION!
db = SQLAlchemy(app)

# Configure logging for better error visibility
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Database Models ---
# --- USER MODEL (Owner Only) ---
class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(512), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # Only 'owner'
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=True)
    owner_code = db.Column(db.String(30), unique=True, nullable=True)

    owned_business = db.relationship('Business', backref='owner', foreign_keys='Business.owner_id')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User(Owner: {self.username}, ID: {self.id})>"

# --- STAFF MODEL ---
class Staff(db.Model):
    __tablename__ = 'staff'

    id = db.Column(db.Integer, primary_key=True)
    staff_code = db.Column(db.String(10), unique=True, nullable=False)  # e.g., SN01
    name = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(128), nullable=False)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    business = db.relationship('Business', backref='staff_members')

    sales = db.relationship('Sale', backref='staff', lazy=True)
    expenses = db.relationship('Expense', backref='staff', lazy=True)
    inventory_updates = db.relationship('Inventory', backref='staff', lazy=True)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def __repr__(self):
        return f"<Staff(Name: {self.name}, Code: {self.staff_code})>"

# --- BUSINESS MODEL ---
class Business(db.Model):
    __tablename__ = 'business'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    business_code_prefix = db.Column(db.String(100), unique=True, nullable=True)

    products = db.relationship('Product', backref='business', lazy=True)
    sales = db.relationship('Sale', backref='business', lazy=True)
    expenses = db.relationship('Expense', backref='business', lazy=True)

    def __repr__(self):
        return f"<Business(Name: {self.name}, Code: {self.business_code_prefix})>"

# --- PRODUCT MODEL ---
class Product(db.Model):
    __tablename__ = 'product'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    cost = db.Column(db.Float, nullable=False)
    in_stock = db.Column(db.Integer, nullable=False, default=0)
    total_sold = db.Column(db.Integer, nullable=False, default=0)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    custom_id = db.Column(db.String(50), unique=True, nullable=True)

    sales = db.relationship('Sale', backref='product', lazy=True, cascade='all, delete-orphan')
    inventory_items = db.relationship('Inventory', backref='product', lazy=True, cascade='all, delete-orphan')

    __table_args__ = (db.UniqueConstraint('name', 'business_id', name='_name_business_uc'),)

    def __repr__(self):
        return f"<Product(Name: {self.name}, Stock: {self.in_stock})>"

# --- SALE MODEL ---
class Sale(db.Model):
    __tablename__ = 'sale'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    quantity = db.Column(db.Integer, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=True)

    def __repr__(self):
        return f"<Sale(Product ID: {self.product_id}, Quantity: {self.quantity})>"

# --- EXPENSE MODEL ---
class Expense(db.Model):
    __tablename__ = 'expense'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100), nullable=True)
    description = db.Column(db.Text, nullable=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=True)

    def __repr__(self):
        return f"<Expense(Category: {self.category}, Amount: {self.amount})>"

# --- INVENTORY MODEL ---
class Inventory(db.Model):
    __tablename__ = 'inventory'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    quantity = db.Column(db.Integer, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=True)

    def __repr__(self):
        return f"<Inventory(Product ID: {self.product_id}, Quantity: {self.quantity})>"

# --- Decorators for Role-Based Access Control ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session and 'staff_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def role_required(role):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            session_role = session.get('role')
            if session_role != role:
                flash(f'Access denied. You must be a {role.capitalize()} to access this page.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- Routes ---

@app.route('/')
def home():
    # --- MODIFIED: Redirect to the new landing page ---
    return redirect(url_for('landing'))

# --- NEW: Landing Page Route ---
@app.route('/landing')
def landing():
    return render_template('landing.html', now=datetime.datetime.utcnow())


@app.route('/register', methods=['GET', 'POST']) 
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        business_name = request.form.get('business_name')

        if not all([username, email, password, business_name]):
            flash('All fields are required to register as a Business Owner.', 'danger')
            return render_template('register.html', now=datetime.datetime.utcnow())

        existing_owner_email = User.query.filter(func.lower(User.email) == func.lower(email), User.role == 'owner').first()
        if existing_owner_email:
            flash('This email is already registered to an owner. Please log in or use a different email.', 'danger')
            return render_template('register.html', now=datetime.datetime.utcnow())

        existing_business = Business.query.filter(func.lower(Business.name) == func.lower(business_name)).first()
        if existing_business:
            flash('A business with this name already exists. Please choose a different name.', 'danger')
            return render_template('register.html', now=datetime.datetime.utcnow())

        try:
            # Step 1: Create user
            new_owner = User(username=username, email=email, role='owner')
            new_owner.set_password(password)
            db.session.add(new_owner)
            db.session.flush()  # ensures new_owner.id is available

            # Step 2: Create business
            new_business = Business(name=business_name, owner_id=new_owner.id)
            db.session.add(new_business)
            db.session.flush()  # ensures new_business.id is available

            # Step 3: Generate business code
            now_dt = datetime.datetime.utcnow()
            year_month = now_dt.strftime('%y%m')
            first_letter = business_name[0].upper()
            padded_id = str(new_business.id).zfill(4)
            business_code = f'BFT/{year_month}/{first_letter}{padded_id}'

            # Step 4: Update business and user
            new_business.business_code_prefix = business_code
            new_owner.business_id = new_business.id  # 🔁 Set owner's business_id here

            # Step 5: Final commit
            db.session.commit()

            flash(f'Business "{business_name}" registered successfully! Your Business Code is: {business_code}. You can now log in.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred during registration: {e}', 'danger')
            app.logger.error(f"Registration error: {e}")

    return render_template('register.html', now=datetime.datetime.utcnow())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('identifier')  # Can be owner email or staff username
        password = request.form.get('password')
        business_name_input = request.form.get('business_name')  # Required for staff

        user = None
        staff_user = None
        business = None

        # --- Try to log in as Owner ---
        if '@' in identifier:
            user = User.query.filter_by(email=identifier, role='owner').first()

        if user and user.check_password(password):
            business = Business.query.filter_by(id=user.business_id).first()
            session['user_id'] = user.id
            session['role'] = 'owner'
            session['business_id'] = user.business_id
            session['username'] = user.username
            session['business_name'] = business.name if business else 'N/A'
            flash(f'Welcome, {user.username}! You are logged in as Business Owner of {session["business_name"]}.', 'success')
            return redirect(url_for('dashboard'))

        # --- Try to log in as Staff ---
        if not business_name_input:
            flash('Business name is required for staff login.', 'danger')
            return render_template('login.html', now=datetime.datetime.utcnow())

        # Get business by name
        business = Business.query.filter(func.lower(Business.name) == func.lower(business_name_input)).first()
        if not business:
            flash('Business not found. Please check the name.', 'danger')
            return render_template('login.html', now=datetime.datetime.utcnow())

        # Get staff by username and business
        staff_user = Staff.query.filter_by(name=identifier, business_id=business.id).first()
        if not staff_user:
            flash('Staff account not found for this business.', 'danger')
            return render_template('login.html', now=datetime.datetime.utcnow())

        if staff_user.password != password:
            flash('Incorrect staff password.', 'danger')
            return render_template('login.html', now=datetime.datetime.utcnow())

        # Successful staff login
        session['staff_id'] = staff_user.id
        session['role'] = 'staff'
        session['business_id'] = staff_user.business_id
        session['username'] = staff_user.name
        session['business_name'] = business.name
        flash(f'Welcome, {staff_user.name}! You are logged in as staff of {session["business_name"]}.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('login.html', now=datetime.datetime.utcnow())

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('staff_id', None)  # Add this line
    session.pop('role', None)
    session.pop('business_id', None)
    session.pop('username', None)
    session.pop('business_name', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    user_role = session.get('role')
    business_id = session.get('business_id')

    # Default placeholders
    total_revenue = 0.0
    total_expenses = 0.0
    net_profit = 0.0
    net_profit_percentage = 0.0
    total_daily_sales_count = 0
    expenses_for_dashboard = []
    
    # Default date filters (for owner)
    start_date_filter = datetime.datetime.min
    end_date_filter = datetime.datetime.utcnow()

    if request.method == 'POST':
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')

        try:
            if start_date_str:
                start_date_filter = datetime.datetime.strptime(start_date_str, '%Y-%m-%d')
            if end_date_str:
                end_date_filter = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            if start_date_filter > end_date_filter:
                raise ValueError("Start date after end date.")
        except ValueError:
            flash('Invalid date range. Resetting filters.', 'warning')
            start_date_filter = datetime.datetime.min
            end_date_filter = datetime.datetime.utcnow()

    # --- Owner Dashboard ---
    if user_role == 'owner':
        user = User.query.get(session['user_id'])

        sales_in_range = Sale.query.filter(
            Sale.business_id == business_id,
            Sale.date >= start_date_filter,
            Sale.date <= end_date_filter
        ).all()

        total_revenue = sum(sale.quantity * sale.total_amount for sale in sales_in_range)

        expenses_in_range = Expense.query.filter(
            Expense.business_id == business_id,
            Expense.date >= start_date_filter,
            Expense.date <= end_date_filter
        ).all()

        total_expenses = sum(exp.amount for exp in expenses_in_range)
        net_profit = total_revenue - total_expenses
        net_profit_percentage = (net_profit / total_revenue) * 100 if total_revenue > 0 else 0.0

        expenses_for_dashboard = Expense.query.filter_by(
            business_id=business_id
        ).order_by(Expense.date.desc()).limit(5).all()

    # --- Staff Dashboard ---
    elif user_role == 'staff':
        user = Staff.query.get(session['staff_id'])
        today = datetime.date.today()
        start_of_day = datetime.datetime.combine(today, datetime.time.min)
        end_of_day = datetime.datetime.combine(today, datetime.time.max)

        staff_sales_today = Sale.query.filter(
            Sale.staff_id == user.id,
            Sale.business_id == business_id,
            Sale.date >= start_of_day,
            Sale.date <= end_of_day
        ).all()

        total_daily_sales_count = len(staff_sales_today)

    # Shared between roles: recent products and sales
    products_list = Product.query.filter_by(
        business_id=business_id
    ).order_by(Product.id.desc()).limit(5).all()

    dashboard_products = [
        {'product': product, 'in_stock': product.in_stock, 'total_sold': product.total_sold}
        for product in products_list
    ]

    sales = Sale.query.filter_by(
        business_id=business_id
    ).order_by(Sale.date.desc()).limit(5).all()

    start_date_form = (
        start_date_filter.strftime('%Y-%m-%d') if start_date_filter != datetime.datetime.min else ''
    )
    end_date_form = (
        end_date_filter.strftime('%Y-%m-%d') if end_date_filter != datetime.datetime.utcnow() else ''
    )

    return render_template('dashboard.html',
        user=user,
        user_role=user_role,
        total_revenue=total_revenue,
        total_expenses=total_expenses,
        net_profit=net_profit,
        net_profit_percentage=net_profit_percentage,
        total_daily_sales_count=total_daily_sales_count,
        products=dashboard_products,
        sales=sales,
        expenses=expenses_for_dashboard,
        start_date_form=start_date_form,
        end_date_form=end_date_form,
        now=datetime.datetime.utcnow()
    )

# --- Product Management Routes ---

@app.route('/products')
@login_required
def products():
    user_business_id = session.get('business_id')
    # --- MODIFIED: Get search query from URL parameter for product search ---
    search_query = request.args.get('search', '').strip() 

    products_list = Product.query.filter_by(business_id=user_business_id)

    # --- MODIFIED: Filter products by name or custom_id if search query is present ---
    if search_query:
        products_list = products_list.filter(
            (Product.name.ilike(f'%{search_query}%')) |
            (Product.custom_id.ilike(f'%{search_query}%'))
        )
    
    products_list = products_list.all() # Execute the query
    
    product_data = []
    for product in products_list:
        product_data.append({
            'product': product,
            'in_stock': product.in_stock,
            'total_sold': product.total_sold,
        })

    # --- MODIFIED: Pass search_query to template for persistent search bar content ---
    return render_template('products.html', product_data=product_data, search_query=search_query, now=datetime.datetime.utcnow())


@app.route('/add_product', methods=['GET', 'POST'])
@role_required('owner')
def add_product():
    user_business_id = session.get('business_id')
    if request.method == 'POST':
        name = request.form.get('product_name') 
        price = request.form.get('selling_price')    
        cost = request.form.get('cost_price')       
        in_stock = request.form.get('in_stock')    
        total_sold = request.form.get('total_sold') 

        if not all([name, price, cost, in_stock, total_sold is not None]):
            flash('Product name, selling price, cost price, in stock, and total sold are required.', 'danger')
            return render_template('add_product.html', now=datetime.datetime.utcnow())

        try:
            price = float(price)
            cost = float(cost)
            in_stock = int(in_stock)
            total_sold = int(total_sold)
            
            if price <= 0 or cost <= 0:
                flash('Selling Price and Cost Price must be positive numbers.', 'danger')
                return render_template('add_product.html', now=datetime.datetime.utcnow())
            if in_stock < 0: 
                flash('In Stock quantity cannot be negative.', 'danger')
                return render_template('add_product.html', now=datetime.datetime.utcnow())
            if total_sold < 0: 
                flash('Total Sold quantity cannot be negative.', 'danger')
                return render_template('add_product.html', now=datetime.datetime.utcnow())

        except ValueError:
            flash('Price, Cost, In Stock, and Total Sold must be valid numbers.', 'danger')
            return render_template('add_product.html', now=datetime.datetime.utcnow())

        existing_product = Product.query.filter_by(name=name, business_id=user_business_id).first()
        if existing_product:
            flash('Product with this name already exists in your business.', 'danger')
            return render_template('add_product.html', now=datetime.datetime.utcnow())

        new_product = Product(name=name, price=price, cost=cost, 
                              in_stock=in_stock, total_sold=total_sold, 
                              business_id=user_business_id)
        try:
            db.session.add(new_product)
            db.session.flush() # Assigns an ID to new_product without committing to the DB yet

            # Now generate custom_id using the obtained new_product.id
            business = db.session.get(Business, new_product.business_id) 
            # Changed from business.business_code to business.business_code_prefix
            business_code_part = business.business_code_prefix.split('/')[-1] if business and business.business_code_prefix else 'XXXX' 
            now_dt = datetime.datetime.utcnow()
            year_month_suffix = now_dt.strftime('%y%m') # Last two digits of year and month
            product_number = str(new_product.id).zfill(3) # Auto-incremented ID, 3 digits
            new_product.custom_id = f'Prd/{year_month_suffix}/{business_code_part}/{product_number}' # Updated Product ID format
            
            db.session.commit() # Now commit everything

            flash(f'Product "{name}" added successfully with {in_stock} units in stock! ID: {new_product.custom_id}', 'success') 
            return redirect(url_for('products'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {e}', 'danger')
            app.logger.error(f"Error adding product: {e}")


    return render_template('add_product.html', now=datetime.datetime.utcnow())

@app.route('/restock_product/<int:product_id>', methods=['GET', 'POST'])
@login_required 
def restock_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.business_id != session.get('business_id'):
        flash("Access denied to this product.", "danger")
        return redirect(url_for('products'))

    current_stock = product.in_stock 

    if request.method == 'POST':
        quantity_to_add = request.form.get('quantity')
        if not quantity_to_add or not quantity_to_add.isdigit() or int(quantity_to_add) <= 0:
            flash('Please enter a valid positive quantity to restock.', 'danger')
            return render_template('restock_product.html', product=product, current_stock=current_stock, now=datetime.datetime.utcnow())
        
        try:
            product.in_stock += int(quantity_to_add)
            
            new_inventory_log = Inventory(
                product_id=product.id, 
                quantity=int(quantity_to_add),
                staff_id = session.get('staff_id') if session.get('role') == 'staff' else session.get('user_id'), # Changed 'users_id' to 'user_id'
                # Removed business_id from Inventory creation as it's not in the SQL schema
            )
            db.session.add(new_inventory_log)
            
            db.session.commit()
            flash(f'{quantity_to_add} units of "{product.name}" restocked successfully!', 'success')
            return redirect(url_for('products'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred during restock: {e}', 'danger')
            app.logger.error(f"Error restock product {product_id}: {e}")


    return render_template('restock_product.html', product=product, current_stock=current_stock, now=datetime.datetime.utcnow())

@app.route('/sell_product', methods=['GET', 'POST'])
@login_required
def sell_product():
    import datetime
    user_role = session.get('role')
    business_id = session.get('business_id')
    products = Product.query.filter_by(business_id=business_id).all()

    # Handle optional product_id in GET request
    product = None
    product_id = request.args.get('product_id')
    if product_id:
        try:
            product_id = int(product_id)
            product = Product.query.get(product_id)
            if not product or product.business_id != business_id:
                product = None
        except ValueError:
            product = None

    if request.method == 'POST':
        product_id = request.form.get('product_id')
        quantity = request.form.get('quantity')
        price = request.form.get('price')

        if not all([product_id, quantity, price]):
            flash('All fields are required.', 'danger')
            return render_template('sell_product.html', products=products, product=product, now=datetime.datetime.utcnow())

        try:
            product_id = int(product_id)
            quantity = int(quantity)
            price = float(price)
        except ValueError:
            flash('Quantity and price must be numeric.', 'danger')
            return render_template('sell_product.html', products=products, product=product, now=datetime.datetime.utcnow())

        if quantity <= 0 or price <= 0:
            flash('Quantity and price must be positive.', 'danger')
            return render_template('sell_product.html', products=products, product=product, now=datetime.datetime.utcnow())

        product = Product.query.get(product_id)
        if not product or product.business_id != business_id:
            flash('Invalid product.', 'danger')
            return render_template('sell_product.html', products=products, product=product, now=datetime.datetime.utcnow())

        if product.in_stock < quantity:
            flash(f'Not enough stock. Available: {product.in_stock}', 'danger')
            return render_template('sell_product.html', products=products, product=product, now=datetime.datetime.utcnow())

        try:
            # Get staff_id or owner user_id
            if user_role == 'staff':
                staff_id = session.get('staff_id')
            else:
                staff_id = session.get('user_id')  # Owner

            # Record Sale
            sale = Sale(
                product_id=product.id,
                quantity=quantity,
                total_amount=price,
                business_id=business_id,
                staff_id=staff_id
            )
            db.session.add(sale)

            # Update stock and inventory log
            product.in_stock -= quantity
            product.total_sold += quantity

            inventory_log = Inventory(
                product_id=product.id,
                quantity=-quantity,
                staff_id=staff_id
            )
            db.session.add(inventory_log)

            db.session.commit()
            flash(f'Successfully sold {quantity} units of {product.name}.', 'success')
            return redirect(url_for('sales'))

        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {e}', 'danger')
            app.logger.error(f'Sale error: {e}')

    return render_template('sell_product.html', products=products, product=product, now=datetime.datetime.utcnow())

@app.route('/delete_product/<int:product_id>', methods=['POST'])
@role_required('owner') 
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)

    if product.business_id != session.get('business_id'):
        flash("Access denied. You can only delete products from your own business.", "danger")
        return redirect(url_for('products'))

    try:
        db.session.delete(product)
        db.session.commit()
        flash(f'Product "{product.name}" (ID: {product.custom_id if product.custom_id else product.id}) has been deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while deleting the product: {e}', 'danger')
        app.logger.error(f"Error deleting product {product_id}: {e}") 
    
    return redirect(url_for('products'))


# --- Sales Record Section ---
@app.route('/sales')
@login_required
def sales():
    user_business_id = session.get('business_id')
    sales = Sale.query.filter_by(business_id=user_business_id).order_by(Sale.date.desc()).all()
    return render_template('sales.html', sales=sales, now=datetime.datetime.utcnow())

@app.route('/record_sale', methods=['GET', 'POST'])
@login_required
def record_sale():
    user_id = session.get('user_id')
    staff_id = session.get('staff_id')  # This will be None for owners
    business_id = session.get('business_id')
    user_role = session.get('role')
    products = Product.query.filter_by(business_id=business_id).all()

    if request.method == 'POST':
        product_id = request.form.get('product_id')
        quantity = request.form.get('quantity_sold')
        sale_price = request.form.get('sale_price')

        if not all([product_id, quantity, sale_price]):
            flash('All fields are required.', 'danger')
            return render_template('record_sale.html', products=products, now=datetime.datetime.utcnow())

        try:
            product_id = int(product_id)
            quantity = int(quantity)
            sale_price = float(sale_price)

            if quantity <= 0 or sale_price <= 0:
                flash('Quantity and Sale Price must be positive numbers.', 'danger')
                return render_template('record_sale.html', products=products, now=datetime.datetime.utcnow())

        except ValueError:
            flash('Invalid input. Use numbers only.', 'danger')
            return render_template('record_sale.html', products=products, now=datetime.datetime.utcnow())

        product = Product.query.get(product_id)
        if not product or product.business_id != business_id:
            flash('Invalid product selected.', 'danger')
            return render_template('record_sale.html', products=products, now=datetime.datetime.utcnow())

        if quantity > product.in_stock:
            flash(f'Only {product.in_stock} units of "{product.name}" are available.', 'danger')
            return render_template('record_sale.html', products=products, now=datetime.datetime.utcnow())

        try:
            # Determine who is recording the sale
            if user_role == 'staff':
                if not staff_id:
                    flash('Unauthorized: staff ID not found in session.', 'danger')
                    return redirect(url_for('login'))
                staff = Staff.query.get(staff_id)
                if not staff:
                    flash("Invalid staff account.", 'danger')
                    return redirect(url_for('login'))
                sale_staff_id = staff.id
            else:
                sale_staff_id = None  # Owner sale

            # Create sale record
            new_sale = Sale(
                product_id=product.id,
                quantity=quantity,
                total_amount=sale_price,
                business_id=business_id,
                staff_id=sale_staff_id
            )
            db.session.add(new_sale)
            db.session.flush()

            # Create inventory log
            new_inventory_log = Inventory(
                product_id=product.id,
                quantity=-quantity,
                staff_id=sale_staff_id
            )
            db.session.add(new_inventory_log)

            # Update stock and total sold
            product.in_stock -= quantity
            product.total_sold += quantity

            db.session.commit()
            flash(f'Sale recorded: {quantity} units of "{product.name}"!', 'success')
            return redirect(url_for('sales'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error: {e}', 'danger')
            app.logger.error(f"Sale error: {e}")

    return render_template('record_sale.html', products=products, now=datetime.datetime.utcnow())

# --- Expense Records Section ---
@app.route('/expenses')
@login_required
def expenses():
    user_business_id = session.get('business_id')
    expenses = Expense.query.filter_by(business_id=user_business_id).order_by(Expense.date.desc()).all() # Changed expense_date to date
    return render_template('expenses.html', expenses=expenses, now=datetime.datetime.utcnow())

@app.route('/add_expense', methods=['GET', 'POST'])
@login_required
def add_expense():
    import datetime
    business_id = session.get('business_id')
    role = session.get('role')

    if request.method == 'POST':
        amount = request.form.get('amount')
        category = request.form.get('category')
        description = request.form.get('description')

        if not all([amount, category, description]):
            flash('All fields are required.', 'danger')
            return redirect(url_for('expenses'))

        try:
            amount = float(amount)
            if amount <= 0:
                flash('Amount must be positive.', 'danger')
                return redirect(url_for('expenses'))

            # Get staff ID only if user is a staff
            if role == 'staff':
                staff_id = session.get('staff_id')

                # Validate that staff ID exists in staff table
                staff = Staff.query.get(staff_id)
                if not staff or staff.business_id != business_id:
                    flash("Invalid staff ID.", "danger")
                    return redirect(url_for('expenses'))
            else:
                staff_id = None  # Owner's expense

            expense = Expense(
                date=datetime.datetime.utcnow(),
                amount=amount,
                category=category,
                description=description,
                business_id=business_id,
                staff_id=staff_id
            )
            db.session.add(expense)
            db.session.commit()
            flash('Expense added successfully.', 'success')
        except ValueError:
            flash('Invalid amount value.', 'danger')
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Error adding expense: {e}')
            flash(f'An error occurred while adding expense: {e}', 'danger')

        return redirect(url_for('expenses'))

    return redirect(url_for('expenses'))

# --- Profile Screen ---
@app.route('/profile')
@login_required
def profile():
    user = User.query.get(session['user_id'])  # Owner only
    business = None
    staff_members = []

    if user.role == 'owner':
        business = Business.query.get(user.business_id)
        if business:
            staff_members = Staff.query.filter_by(business_id=business.id).all()

    return render_template('profile.html', user=user, business=business, staff_members=staff_members, now=datetime.datetime.utcnow())

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required 
def edit_profile():
    user = User.query.get(session['user_id']) # Changed 'users_id' to 'user_id'
    if request.method == 'POST':
        new_username = request.form.get('username')
        new_email = request.form.get('email')

        if not new_username:
            flash('Username cannot be empty.', 'danger')
            return render_template('edit_profile.html', user=user, now=datetime.datetime.utcnow())
        
        if user.role == 'owner':
            if not new_email:
                flash('Email cannot be empty for owner accounts.', 'danger')
                return render_template('edit_profile.html', user=user, now=datetime.datetime.utcnow())
            
            existing_email_user = User.query.filter(User.email == new_email, User.id != user.id, User.role == 'owner').first()
            if existing_email_user:
                flash('This email is already taken by another owner.', 'danger')
                return render_template('edit_profile.html', user=user, now=datetime.datetime.utcnow())
        
        if user.role == 'owner':
            existing_username_owner = User.query.filter(
                User.username == new_username, 
                User.id != user.id, 
                User.role == 'owner'
            ).first()
            if existing_username_owner:
                flash('This username is already taken by another owner.', 'danger')
                return render_template('edit_profile.html', user=user, now=datetime.datetime.utcnow())
        elif user.role == 'staff':
             existing_username_staff = User.query.filter(
                User.username == new_username, 
                User.business_id == user.business_id, 
                User.id != user.id
            ).first()
             if existing_username_staff:
                flash('This username is already taken by another staff member in your business.', 'danger')
                return render_template('edit_profile.html', user=user, now=datetime.datetime.utcnow())


        user.username = new_username
        user.email = new_email 
        
        try:
            db.session.commit()
            # Update username in session if it changed
            if session.get('username') != user.username:
                session['username'] = user.username
            flash('Your profile has been updated successfully!', 'success')
            return redirect(url_for('profile'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred while updating your profile: {e}', 'danger')

    return render_template('edit_profile.html', user=user, now=datetime.datetime.utcnow())


@app.route('/change_password', methods=['GET', 'POST'])
@login_required 
def change_password():
    user = User.query.get(session['user_id']) # Changed 'users_id' to 'user_id'
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not user.check_password(current_password):
            flash('Incorrect current password.', 'danger')
            return render_template('change_password.html', now=datetime.datetime.utcnow())

        if not new_password or not confirm_password:
            flash('New password and confirmation are required.', 'danger')
            return render_template('change_password.html', now=datetime.datetime.utcnow())

        if new_password != confirm_password:
            flash('New password and confirmation do not match.', 'danger')
            return render_template('change_password.html', now=datetime.datetime.utcnow())

        if len(new_password) < 6: 
            flash('New password must be at least 6 characters long.', 'danger')
            return render_template('change_password.html', now=datetime.datetime.utcnow())

        user.set_password(new_password)
        try:
            db.session.commit()
            flash('Your password has been changed successfully!', 'success')
            return redirect(url_for('profile'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred while changing your password: {e}', 'danger')

    return render_template('change_password.html', now=datetime.datetime.utcnow())


# --- Staff Management Routes ---

@app.route('/add_staff', methods=['GET', 'POST'])
@login_required
def add_staff():
    if session.get('role') != 'owner':
        flash('Only business owners can add staff.', 'danger')
        return redirect(url_for('dashboard'))

    business_id = session.get('business_id')

    # Enforce 3-staff limit
    if Staff.query.filter_by(business_id=business_id).count() >= 3:
        flash('You have reached the maximum of 3 staff members for your business.', 'warning')
        return redirect(url_for('profile'))

    if request.method == 'POST':
        name = request.form.get('name')
        password = request.form.get('password')

        if not all([name, password]):
            flash('All fields are required.', 'danger')
            return render_template('add_staff.html')

        staff_count = Staff.query.filter_by(business_id=business_id).count()
        staff_code = f"SN{str(staff_count + 1).zfill(2)}"

        new_staff = Staff(
            name=name,
            business_id=business_id,
            staff_code=staff_code
        )
        new_staff.set_password(password)

        try:
            db.session.add(new_staff)
            db.session.commit()
            flash(f'Staff "{name}" added successfully with staff code {staff_code}.', 'success')
            return redirect(url_for('profile'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error adding staff: {e}', 'danger')

    return render_template('add_staff.html')

@app.route('/edit_staff/<int:staff_id>', methods=['GET', 'POST'])
@role_required('owner')
def edit_staff(staff_id):
    staff_member = Staff.query.get_or_404(staff_id)

    if staff_member.business_id != session.get('business_id'):
        flash("Access denied. You can only edit staff in your business.", "danger")
        return redirect(url_for('profile'))

    if request.method == 'POST':
        new_name = request.form.get('name')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not new_name:
            flash('Staff name cannot be empty.', 'danger')
            return render_template('edit_staff.html', staff_member=staff_member, now=datetime.datetime.utcnow())

        # Ensure uniqueness of staff name in same business
        existing_name = Staff.query.filter(
            Staff.name == new_name,
            Staff.business_id == staff_member.business_id,
            Staff.id != staff_member.id
        ).first()
        if existing_name:
            flash('Another staff with this name already exists in your business.', 'danger')
            return render_template('edit_staff.html', staff_member=staff_member, now=datetime.datetime.utcnow())

        staff_member.name = new_name

        if new_password:
            if new_password != confirm_password:
                flash('Passwords do not match.', 'danger')
                return render_template('edit_staff.html', staff_member=staff_member)
            if len(new_password) < 6:
                flash('Password must be at least 6 characters.', 'danger')
                return render_template('edit_staff.html', staff_member=staff_member)
            staff_member.set_password(new_password)

        try:
            db.session.commit()
            flash('Staff updated successfully.', 'success')
            return redirect(url_for('profile'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating staff: {e}', 'danger')

    return render_template('edit_staff.html', staff_member=staff_member, now=datetime.datetime.utcnow())

@app.route('/delete_staff/<int:staff_id>', methods=['POST'])
@role_required('owner')
def delete_staff(staff_id):
    staff_member = Staff.query.get_or_404(staff_id)

    if staff_member.business_id != session.get('business_id'):
        flash("Access denied. You can only delete staff in your business.", "danger")
        return redirect(url_for('profile'))

    try:
        db.session.delete(staff_member)
        db.session.commit()
        flash(f'Staff "{staff_member.name}" deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting staff: {e}', 'danger')

    return redirect(url_for('profile'))

# --- Report Screen (Accessed from Profile) ---
from flask import render_template, request, session, flash
from sqlalchemy import func
import datetime

@app.route('/reports', methods=['GET', 'POST'])
@role_required('owner') 
def reports():
    user_business_id = session.get('business_id')

    # Default to all time
    start_date_filter = datetime.datetime.min
    end_date_filter = datetime.datetime.utcnow()

    if request.method == 'POST':
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')

        try:
            if start_date_str:
                start_date_filter = datetime.datetime.strptime(start_date_str, '%Y-%m-%d')
            if end_date_str:
                end_date_filter = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        except ValueError:
            flash('Invalid date format. Please use YYYY-MM-DD.', 'danger')
            start_date_filter = datetime.datetime.min
            end_date_filter = datetime.datetime.utcnow()

        if start_date_filter > end_date_filter:
            flash('Start date cannot be after end date. Displaying all data.', 'warning')
            start_date_filter = datetime.datetime.min
            end_date_filter = datetime.datetime.utcnow()

    # --- General Financial Metrics ---
    sales_in_range = Sale.query.filter(
        Sale.business_id == user_business_id,
        Sale.date >= start_date_filter,
        Sale.date <= end_date_filter
    ).all()

    total_revenue = sum(sale.quantity * sale.total_amount for sale in sales_in_range)
    total_cost_of_goods_sold = sum(sale.quantity * sale.product.cost for sale in sales_in_range)
    gross_profit = total_revenue - total_cost_of_goods_sold

    expenses_in_range = Expense.query.filter(
        Expense.business_id == user_business_id,
        Expense.date >= start_date_filter,
        Expense.date <= end_date_filter
    ).all()
    total_expenses = sum(exp.amount for exp in expenses_in_range)

    net_profit = total_revenue - total_expenses
    net_profit_percentage = (net_profit / total_revenue) * 100 if total_revenue > 0 else 0.0

    # --- Sales by Product ---
    sales_by_product_query = db.session.query(
        Product.name,
        func.sum(Sale.quantity).label('total_quantity_sold'),
        func.sum(Sale.quantity * Sale.total_amount).label('total_revenue_from_product')
    ).join(Sale).filter(
        Sale.business_id == user_business_id,
        Sale.date >= start_date_filter,
        Sale.date <= end_date_filter
    ).group_by(Product.name).order_by(func.sum(Sale.quantity).desc()).all()

    sales_by_product = [
        {'product_name': s.name, 'quantity_sold': s.total_quantity_sold, 'revenue': s.total_revenue_from_product}
        for s in sales_by_product_query
    ]

    # --- Expenses by Category ---
    expenses_by_category_query = db.session.query(
        Expense.category,
        func.sum(Expense.amount).label('total_amount')
    ).filter(
        Expense.business_id == user_business_id,
        Expense.date >= start_date_filter,
        Expense.date <= end_date_filter
    ).group_by(Expense.category).order_by(func.sum(Expense.amount).desc()).all()

    expenses_by_category = [
        {'category': e.category, 'total_amount': e.total_amount}
        for e in expenses_by_category_query
    ]

    # Prepare form inputs to retain values
    start_date_form = start_date_filter.strftime('%Y-%m-%d') if start_date_filter != datetime.datetime.min else ''
    end_date_form = end_date_filter.strftime('%Y-%m-%d') if end_date_filter.date() != datetime.datetime.utcnow().date() else ''

    return render_template('reports.html',
                           total_revenue=total_revenue,
                           total_expenses=total_expenses,
                           net_profit=net_profit,
                           gross_profit=gross_profit, 
                           net_profit_percentage=net_profit_percentage,
                           sales_by_product=sales_by_product,
                           expenses_by_category=expenses_by_category,
                           start_date_form=start_date_form,
                           end_date_form=end_date_form,
                           now=datetime.datetime.utcnow())

@app.route('/init-db')
def init_db():
    with app.app_context():
        db.create_all()
    return "Database tables created!"

# --- Run the Application ---
if __name__ == '__main__':
    app.run(debug=True)
