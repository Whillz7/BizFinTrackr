import datetime
import os
import logging
import psycopg2 # type: ignore
import socket

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from sqlalchemy import event, func, and_
from werkzeug.security import check_password_hash, generate_password_hash

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

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=False, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True) # Changed to nullable=True as per SQL
    password_hash = db.Column(db.String(512), nullable=False)
    role = db.Column(db.String(10), nullable=False)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=True) # Changed to nullable=True as per SQL

    # Removed __table_args__ as it's not present in the SQL schema for users table
    # Removed owned_business relationship as it's defined on the Business side in SQL
    sales = db.relationship('Sale', backref='staff_user', lazy=True)
    expenses = db.relationship('Expense', backref='staff_user', lazy=True)
    inventory_updates = db.relationship('Inventory', backref='staff_user', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"users('{self.username}', '{self.role}', Staff_ID: {self.id}, Business_ID: {self.business_id})"

    @property
    def staff_code(self):
        if self.id is not None:
            return str(self.id).zfill(2)[-2:]
        return 'YY'

class Business(db.Model):
    __tablename__ = 'business'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    business_code_prefix = db.Column(db.String(100), unique=True, nullable=True) # e.g., 'BC/2506/D0001'

    # Updated relationship to match the SQL schema and avoid conflicts
    owner_user = db.relationship(
    'User',
    backref=db.backref('owned_business', uselist=False),
    foreign_keys=[owner_id],
    lazy='joined'
)

    users = db.relationship('User', backref='business', lazy=True, foreign_keys='User.business_id') # Renamed staff to users for clarity
    products = db.relationship('Product', backref='business', lazy=True)
    sales = db.relationship('Sale', backref='business', lazy=True)
    expenses = db.relationship('Expense', backref='business', lazy=True)

    def __repr__(self):
        return f"Business('{self.name}', ID: {self.id}, Code: {self.business_code_prefix})"


class Product(db.Model):
    __tablename__ = 'product'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False) # Selling Price
    cost = db.Column(db.Float, nullable=False)  # Cost Price
    in_stock = db.Column(db.Integer, nullable=False, default=0)
    total_sold = db.Column(db.Integer, nullable=False, default=0) # Cumulative total sold
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    custom_id = db.Column(db.String(50), unique=True, nullable=True) # This can be NULL until generated

    # Ensure product name is unique per business
    __table_args__ = (db.UniqueConstraint('name', 'business_id', name='_name_business_uc'),)

    # Add cascade to delete related inventory and sales records when a product is deleted
    sales = db.relationship('Sale', backref='product', lazy=True, cascade='all, delete-orphan')
    inventory_items = db.relationship('Inventory', backref='product', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f"Product('{self.name}', ID: {self.custom_id if self.custom_id else self.id}, Stock: {self.in_stock})"


class Inventory(db.Model):
    __tablename__ = 'inventory'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow) # Renamed last_updated to date
    quantity = db.Column(db.Integer, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True) # Changed to nullable=True as per SQL
    # Removed business_id from Inventory model as it's not in the SQL schema for inventory table

    def __repr__(self):
        return f"Inventory(Product ID: {self.product_id}, Quantity: {self.quantity}, Updated: {self.date})"


class Sale(db.Model):
    __tablename__ = 'sale'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    quantity = db.Column(db.Integer, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Either owner or staff

    def __repr__(self):
        return f"Sale(ID: {self.id}, Product ID: {self.product_id}, Qty: {self.quantity})"

class Expense(db.Model):
    __tablename__ = 'expense'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow) # Renamed expense_date to date
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100), nullable=True) # Changed to nullable=True and length to 100 as per SQL
    description = db.Column(db.Text, nullable=True) # Changed to nullable=True and type to Text as per SQL
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True) # Changed to nullable=True as per SQL

    def __repr__(self):
        return f"Expense('{self.description}', Amount: {self.amount:.2f}, Date: {self.date})"


# --- Decorators for Role-Based Access Control ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session: # Changed 'users_id' to 'user_id'
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(role):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if session.get('role') != role:
                flash(f'Access denied. You must be a {role.capitalize()} to view this page.', 'danger')
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
        business_name_input = request.form.get('business_name')  # New field for staff login

        user = None
        business = None

        # Try to log in as owner (email or username)
        if '@' in identifier:
            user = User.query.filter_by(email=identifier, role='owner').first()

        if not user:  # If not found by email or not an owner email, try by username
            user = User.query.filter_by(username=identifier).first()

        if user:
            if user.role == 'owner':
                # Safely fetch owned business
                business = Business.query.filter_by(owner_id=user.id).first()

                if business_name_input and business and business.name.lower() != business_name_input.lower():
                    flash('Business name does not match your owner account. Please ensure it is correct.', 'danger')
                    return render_template('login.html', now=datetime.datetime.utcnow())

            elif user.role == 'staff':
                if not business_name_input:
                    flash('Business name is required for staff login.', 'danger')
                    return render_template('login.html', now=datetime.datetime.utcnow())

                # Match business name (case-insensitive)
                business_from_input = Business.query.filter(func.lower(Business.name) == func.lower(business_name_input)).first()

                if not business_from_input or user.business_id != business_from_input.id:
                    flash('Invalid business name or staff not associated with this business.', 'danger')
                    return render_template('login.html', now=datetime.datetime.utcnow())

                business = business_from_input

            # If user and business checks pass, proceed with password check
            if user.check_password(password):
                session['user_id'] = user.id
                session['role'] = user.role
                session['business_id'] = user.business_id
                session['username'] = user.username
                session['business_name'] = business.name if business else 'N/A'
                flash(f'Welcome, {user.username}! You are logged in as {user.role} of {session["business_name"]}.', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Login Unsuccessful. Incorrect password.', 'danger')
        else:
            flash('Login Unsuccessful. User not found.', 'danger')

    return render_template('login.html', now=datetime.datetime.utcnow())


@app.route('/logout')
def logout():
    session.pop('user_id', None) # Changed 'users_id' to 'user_id'
    session.pop('role', None)
    session.pop('business_id', None)
    session.pop('username', None) 
    # --- MODIFIED: Clear business name from session on logout ---
    session.pop('business_name', None) 
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    user = User.query.get(session['user_id']) # Changed 'users_id' to 'user_id'
    user_role = session.get('role')
    user_business_id = session.get('business_id')

    # Initialize variables for template
    total_revenue = 0.0
    total_expenses = 0.0
    net_profit = 0.0
    net_profit_percentage = 0.0
    
    products_sold_month = 0 
    total_daily_sales_count = 0 

    # Default date range for owner's metrics (very broad)
    start_date_filter = datetime.datetime.min # Default to earliest possible date
    end_date_filter = datetime.datetime.utcnow() # Default to current date and time

    if request.method == 'POST':
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')

        if start_date_str:
            try:
                start_date_filter = datetime.datetime.strptime(start_date_str, '%Y-%m-%d')
            except ValueError:
                flash('Invalid start date format. Please use YYYY-MM-DD.', 'danger')
                # Keep default or previous valid date
        
        if end_date_str:
            try:
                end_date_filter = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            except ValueError:
                flash('Invalid end date format. Please use YYYY-MM-DD.', 'danger')
                # Keep default or previous valid date
        
        if start_date_filter > end_date_filter:
            flash('Start date cannot be after end date. Resetting date filter.', 'warning')
            start_date_filter = datetime.datetime.min
            end_date_filter = datetime.datetime.utcnow()

    # Get string representation for form fields (defaults or user selection)
    start_date_form = start_date_filter.strftime('%Y-%m-%d') if start_date_filter != datetime.datetime.min else ''
    end_date_form = end_date_filter.strftime('%Y-%m-%d') if end_date_filter != datetime.datetime.utcnow() else ''


    if user_role == 'owner':
        # Apply date filter to sales and expenses queries
        sales_in_range = Sale.query.filter(
            Sale.business_id == user_business_id,
            Sale.date >= start_date_filter, # Changed sale_date to date
            Sale.date <= end_date_filter # Changed sale_date to date
        ).all()
        total_revenue = sum(sale.quantity * sale.total_amount for sale in sales_in_range) # Changed quantity_sold to quantity and sale_price to total_amount
        
        expenses_in_range = Expense.query.filter(
            Expense.business_id == user_business_id,
            Expense.date >= start_date_filter, # Changed expense_date to date
            Expense.date <= end_date_filter # Changed expense_date to date
        ).all()
        total_expenses = sum(expense.amount for expense in expenses_in_range)
        
        net_profit = total_revenue - total_expenses

        if total_revenue > 0:
            net_profit_percentage = (net_profit / total_revenue) * 100
        else:
            net_profit_percentage = 0.0 # Avoid division by zero


        expenses_for_dashboard = Expense.query.filter_by(business_id=user_business_id).order_by(Expense.date.desc()).limit(5).all() # Changed expense_date to date

    elif user_role == 'staff':
        today = datetime.date.today()
        start_of_day = datetime.datetime.combine(today, datetime.time.min)
        end_of_day = datetime.datetime.combine(today, datetime.time.max)

        staff_sales_today = Sale.query.filter(
            Sale.staff_id == user.id,
            Sale.business_id == user_business_id,
            Sale.date >= start_of_day, # Changed sale_date to date
            Sale.date <= end_of_day # Changed sale_date to date
        ).all()
        total_daily_sales_count = len(staff_sales_today) 
        
        expenses_for_dashboard = [] # Staff don't see general expenses on dashboard

    # --- MODIFIED: Dashboard recent products list to match products.html format ---
    products_list = Product.query.filter_by(business_id=user_business_id).order_by(Product.id.desc()).limit(5).all()
    # Format products for dashboard to match products.html format
    dashboard_products = []
    for product in products_list:
        dashboard_products.append({
            'product': product,
            'in_stock': product.in_stock,
            'total_sold': product.total_sold,
        })

    sales = Sale.query.filter_by(business_id=user_business_id).order_by(Sale.date.desc()).limit(5).all() # Changed sale_date to date
    
    return render_template('dashboard.html',
                            user=user,
                            user_role=user_role,
                            total_revenue=total_revenue,
                            total_expenses=total_expenses, 
                            net_profit=net_profit,
                            net_profit_percentage=net_profit_percentage, 
                            total_daily_sales_count=total_daily_sales_count, 
                            products=dashboard_products, # Changed to dashboard_products
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
                staff_id=session['user_id'], # Changed 'users_id' to 'user_id'
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


@app.route('/sell_product/<int:product_id>', methods=['GET', 'POST'])
@login_required 
def sell_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.business_id != session.get('business_id'):
        flash("Access denied to this product.", "danger")
        return redirect(url_for('products'))
        
    current_stock = product.in_stock 

    if request.method == 'POST':
        quantity_to_sell = request.form.get('quantity')
        sale_price_override = request.form.get('sale_price') # New field for actual sale price

        if not all([quantity_to_sell, sale_price_override is not None]):
            flash('Quantity and Sale Price are required.', 'danger')
            return render_template('sell_product.html', product=product, current_stock=current_stock, now=datetime.datetime.utcnow())
        
        try:
            quantity_to_sell = int(quantity_to_sell)
            sale_price_override = float(sale_price_override)

            if quantity_to_sell <= 0:
                flash('Please enter a valid positive quantity to sell.', 'danger')
                return render_template('sell_product.html', product=product, current_stock=current_stock, now=datetime.datetime.utcnow())
            
            if sale_price_override <= 0:
                flash('Sale price must be a positive number.', 'danger')
                return render_template('sell_product.html', product=product, current_stock=current_stock, now=datetime.datetime.utcnow())

        except ValueError:
            flash('Quantity and Sale Price must be valid numbers.', 'danger')
            return render_template('sell_product.html', product=product, current_stock=current_stock, now=datetime.datetime.utcnow())

        if quantity_to_sell > current_stock:
            flash(f'Not enough stock. Only {current_stock} units of "{product.name}" available.', 'danger')
            return render_template('sell_product.html', product=product, current_stock=current_stock, now=datetime.datetime.utcnow())
        
        try:
            product.in_stock -= quantity_to_sell
            product.total_sold += quantity_to_sell 
            
            new_sale = Sale(
                product_id=product.id,
                quantity=quantity_to_sell, # Changed quantity_sold to quantity
                total_amount=sale_price_override, # Changed sale_price to total_amount
                staff_id=session['user_id'], # Changed 'users_id' to 'user_id'
                business_id=session['business_id']
            )
            db.session.add(new_sale)
            db.session.flush() # Assigns an ID to new_sale without committing to the DB yet

            # Removed custom_id generation as it's not in the SQL schema for sale table
            
            new_inventory_log = Inventory(
                product_id=new_sale.product.id, 
                quantity=-new_sale.quantity, # Changed quantity_sold to quantity
                staff_id=session['user_id'], # Changed 'users_id' to 'user_id'
                # Removed business_id from Inventory creation as it's not in the SQL schema
            )
            db.session.add(new_inventory_log)

            db.session.commit() # Now commit everything
            flash(f'{quantity_to_sell} units of "{product.name}" sold successfully! Sale ID: {new_sale.id}', 'success') # Changed custom_id to id
            return redirect(url_for('products'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred during sale: {e}', 'danger')
            app.logger.error(f"Error selling product {product_id}: {e}")

    return render_template('sell_product.html', product=product, current_stock=current_stock, now=datetime.datetime.utcnow())


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
    user_business_id = session.get('business_id')
    products_for_sale = Product.query.filter_by(business_id=user_business_id).all()

    if request.method == 'POST':
        product_id = request.form.get('product_id')
        quantity_sold = request.form.get('quantity_sold')
        sale_price_override = request.form.get('sale_price')

        if not all([product_id, quantity_sold, sale_price_override]):
            flash('Product, Quantity, and Sale Price are required.', 'danger')
            return render_template('record_sale.html', products=products_for_sale, now=datetime.datetime.utcnow())

        try:
            product_id = int(product_id)
            quantity_sold = int(quantity_sold)
            sale_price_override = float(sale_price_override)

            if quantity_sold <= 0 or sale_price_override <= 0:
                flash('Quantity and Sale Price must be positive numbers.', 'danger')
                return render_template('record_sale.html', products=products_for_sale, now=datetime.datetime.utcnow())

        except ValueError:
            flash('Product ID, Quantity, and Sale Price must be valid numbers.', 'danger')
            return render_template('record_sale.html', products=products_for_sale, now=datetime.datetime.utcnow())

        product = Product.query.get(product_id)
        if not product or product.business_id != user_business_id:
            flash('Invalid product selected.', 'danger')
            return render_template('record_sale.html', products=products_for_sale, now=datetime.datetime.utcnow())

        if quantity_sold > product.in_stock:
            flash(f'Not enough stock. Only {product.in_stock} units of "{product.name}" available.', 'danger')
            return render_template('record_sale.html', products=products_for_sale, now=datetime.datetime.utcnow())

@app.route('/record_sale', methods=['GET', 'POST'])
@login_required 
def record_sale():
    user_id = session.get('user_id')
    user_business_id = session.get('business_id')
    user_role = session.get('role')
    products_for_sale = Product.query.filter_by(business_id=user_business_id).all()

    if request.method == 'POST':
        product_id = request.form.get('product_id')
        quantity_sold = request.form.get('quantity_sold')
        sale_price_override = request.form.get('sale_price')

        if not all([product_id, quantity_sold, sale_price_override]):
            flash('Product, Quantity, and Sale Price are required.', 'danger')
            return render_template('record_sale.html', products=products_for_sale, now=datetime.datetime.utcnow())

        try:
            product_id = int(product_id)
            quantity_sold = int(quantity_sold)
            sale_price_override = float(sale_price_override)

            if quantity_sold <= 0 or sale_price_override <= 0:
                flash('Quantity and Sale Price must be positive numbers.', 'danger')
                return render_template('record_sale.html', products=products_for_sale, now=datetime.datetime.utcnow())

        except ValueError:
            flash('Product ID, Quantity, and Sale Price must be valid numbers.', 'danger')
            return render_template('record_sale.html', products=products_for_sale, now=datetime.datetime.utcnow())

        product = Product.query.get(product_id)
        if not product or product.business_id != user_business_id:
            flash('Invalid product selected.', 'danger')
            return render_template('record_sale.html', products=products_for_sale, now=datetime.datetime.utcnow())

        if quantity_sold > product.in_stock:
            flash(f'Not enough stock. Only {product.in_stock} units of "{product.name}" available.', 'danger')
            return render_template('record_sale.html', products=products_for_sale, now=datetime.datetime.utcnow())

        try:
            # Update product stock and sales count
            product.in_stock -= quantity_sold
            product.total_sold += quantity_sold 

            # Prepare sale record
            sale_data = {
                'product_id': product.id,
                'quantity': quantity_sold,
                'total_amount': sale_price_override,
                'business_id': user_business_id
            }

            if user_role == 'staff':
                sale_data['staff_id'] = user_id  # Only set if staff

            new_sale = Sale(**sale_data)
            db.session.add(new_sale)
            db.session.flush()

            # Prepare inventory log
            inventory_data = {
                'product_id': product.id,
                'quantity': -quantity_sold
            }

            if user_role == 'staff':
                inventory_data['staff_id'] = user_id  # Only set if staff

            new_inventory_log = Inventory(**inventory_data)
            db.session.add(new_inventory_log)

            db.session.commit()
            flash(f'Sale recorded for {quantity_sold} units of "{product.name}"! Sale ID: {new_sale.id}', 'success')
            return redirect(url_for('sales'))

        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred during recording sale: {e}', 'danger')
            app.logger.error(f"Error recording sale: {e}")

    return render_template('record_sale.html', products=products_for_sale, now=datetime.datetime.utcnow())

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
    if request.method == 'POST':
        description = request.form.get('description')
        amount = request.form.get('amount')
        category = request.form.get('category')
        
        if not all([description, amount, category]):
            flash('All expense fields are required.', 'danger')
            return render_template('add_expense.html', now=datetime.datetime.utcnow())
        
        try:
            amount = float(amount)
            if amount <= 0:
                flash('Amount must be a positive number.', 'danger')
                return render_template('add_expense.html', now=datetime.datetime.utcnow())
        except ValueError:
            flash('Amount must be a valid number.', 'danger')
            return render_template('add_expense.html', now=datetime.datetime.utcnow())
        
        new_expense = Expense(
            description=description,
            amount=amount,
            category=category,
            staff_id=session['user_id'], # Changed 'users_id' to 'user_id'
            business_id=session['business_id']
        )
        try:
            db.session.add(new_expense)
            db.session.commit()
            flash(f'Expense "{description}" of ${amount:.2f} recorded successfully!', 'success')
            return redirect(url_for('expenses'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred while adding expense: {e}', 'danger')
            app.logger.error(f"Error adding expense: {e}")

    return render_template('add_expense.html', now=datetime.datetime.utcnow())


# --- Profile Screen ---
@app.route('/profile')
@login_required
def profile():
    user = User.query.get(session['user_id']) # Changed 'users_id' to 'user_id'
    business = None
    if user.role == 'owner':
        business = Business.query.get(user.business_id)
    
    staff_members = []
    if user.role == 'owner' and business:
        staff_members = User.query.filter_by(business_id=business.id).filter(User.role=='staff').all()
    
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
@role_required('owner')
def add_staff():
    owner_user = User.query.get(session['user_id'])
    owner_business = owner_user.owned_business

    if not owner_business:
        flash("You do not have an associated business. Please contact support.", "danger")
        return redirect(url_for('dashboard'))

    STAFF_LIMIT_PER_BUSINESS = 3
    current_staff_count = User.query.filter_by(business_id=owner_business.id, role='staff').count()

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Username and password are required for staff registration.', 'danger')
            return render_template('add_staff.html', current_staff_count=current_staff_count, staff_limit=STAFF_LIMIT_PER_BUSINESS, owner_user=owner_user, now=datetime.datetime.utcnow())

        existing_staff = User.query.filter_by(username=username, business_id=owner_business.id, role='staff').first()
        if existing_staff:
            flash('Username already exists for a staff member in your business.', 'danger')
            return render_template('add_staff.html', current_staff_count=current_staff_count, staff_limit=STAFF_LIMIT_PER_BUSINESS, owner_user=owner_user, now=datetime.datetime.utcnow())

        if current_staff_count >= STAFF_LIMIT_PER_BUSINESS:
            flash(f'You have reached the maximum of {STAFF_LIMIT_PER_BUSINESS} staff members.', 'danger')
            return render_template('add_staff.html', current_staff_count=current_staff_count, staff_limit=STAFF_LIMIT_PER_BUSINESS, owner_user=owner_user, now=datetime.datetime.utcnow())

        new_staff = User(
            username=username,
            email=None,
            role='staff',
            business_id=owner_business.id
        )
        new_staff.set_password(password)

        try:
            db.session.add(new_staff)
            db.session.commit()
            flash(f'Staff member "{username}" added successfully to {owner_business.name}!', 'success')
            current_staff_count += 1
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred while adding staff: {str(e)}', 'danger')
            app.logger.error(f"Error adding staff: {e}")

    return render_template(
        'add_staff.html',
        current_staff_count=current_staff_count,
        staff_limit=STAFF_LIMIT_PER_BUSINESS,
        owner_user=owner_user,
        now=datetime.datetime.utcnow()
    )

@app.route('/edit_staff/<int:staff_id>', methods=['GET', 'POST'])
@role_required('owner')
def edit_staff(staff_id):
    staff_member = User.query.get_or_404(staff_id)

    if staff_member.business_id != session.get('business_id') or staff_member.role != 'staff':
        flash("Access denied. You can only edit staff members from your own business.", "danger")
        return redirect(url_for('profile'))
    
    if staff_member.id == session.get('user_id'): # Changed 'users_id' to 'user_id'
        flash("You cannot edit your own profile via staff management. Use 'Edit Profile' instead.", "warning")
        return redirect(url_for('profile'))

    if request.method == 'POST':
        new_username = request.form.get('username')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not new_username:
            flash('Username cannot be empty.', 'danger')
            return render_template('edit_staff.html', staff_member=staff_member, now=datetime.datetime.utcnow())

        existing_username_in_business = User.query.filter(
            User.username == new_username,
            User.business_id == session.get('business_id'),
            User.id != staff_member.id
        ).first()
        if existing_username_in_business:
            flash('This username is already taken by another staff member in your business. Choose a different one.', 'danger')
            return render_template('edit_staff.html', staff_member=staff_member, now=datetime.datetime.utcnow())

        staff_member.username = new_username

        if new_password: 
            if new_password != confirm_password:
                flash('New password and confirmation do not match.', 'danger')
                return render_template('edit_staff.html', staff_member=staff_member, now=datetime.datetime.utcnow())
            if len(new_password) < 6:
                flash('New password must be at least 6 characters long.', 'danger')
                return render_template('edit_staff.html', staff_member=staff_member, now=datetime.datetime.utcnow())
            staff_member.set_password(new_password)
        
        try:
            db.session.commit()
            flash(f'Staff member "{staff_member.username}" details updated successfully!', 'success')
            return redirect(url_for('profile'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred while updating staff member: {e}', 'danger')
            app.logger.error(f"Error editing staff {staff_id}: {e}")

    return render_template('edit_staff.html', staff_member=staff_member, now=datetime.datetime.utcnow())


@app.route('/delete_staff/<int:staff_id>', methods=['POST'])
@role_required('owner')
def delete_staff(staff_id):
    staff_member = User.query.get_or_404(staff_id)

    if staff_member.business_id != session.get('business_id') or staff_member.role != 'staff':
        flash("Access denied. You can only delete staff members from your own business.", "danger")
        return redirect(url_for('profile'))

    if staff_member.id == session.get('user_id'): # Changed 'users_id' to 'user_id'
        flash("You cannot delete your own account from staff management.", "danger")
        return redirect(url_for('profile'))

    try:
        db.session.delete(staff_member)
        db.session.commit()
        flash(f'Staff member "{staff_member.username}" has been deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while deleting staff member: {e}', 'danger')
        app.logger.error(f"Error deleting staff member: {e}")
    
    return redirect(url_for('profile'))


# --- Report Screen (Accessed from Profile) ---
@app.route('/reports', methods=['GET', 'POST'])
@role_required('owner') 
def reports():
    user_business_id = session.get('business_id')

    # Default date range for reports
    start_date_filter = datetime.datetime.min
    end_date_filter = datetime.datetime.utcnow()

    if request.method == 'POST':
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')

        if start_date_str:
            try:
                start_date_filter = datetime.datetime.strptime(start_date_str, '%Y-%m-%d')
            except ValueError:
                flash('Invalid start date format. Please use YYYY-MM-DD.', 'danger')
                start_date_filter = datetime.datetime.min # Reset to default on error
        
        if end_date_str:
            try:
                # Set end of day for the selected date
                end_date_filter = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            except ValueError:
                flash('Invalid end date format. Please use YYYY-MM-DD.', 'danger')
                end_date_filter = datetime.datetime.utcnow() # Reset to default on error
        
        if start_date_filter > end_date_filter:
            flash('Start date cannot be after end date. Displaying all available data.', 'warning')
            start_date_filter = datetime.datetime.min
            end_date_filter = datetime.datetime.utcnow()

    # --- General Financial Metrics ---
    sales_in_range = Sale.query.filter(
        Sale.business_id == user_business_id,
        Sale.date >= start_date_filter, # Changed sale_date to date
        Sale.date <= end_date_filter # Changed sale_date to date
    ).all()
    total_revenue = sum(sale.quantity * sale.total_amount for sale in sales_in_range) # Changed quantity_sold to quantity and sale_price to total_amount
    total_cost_of_goods_sold = sum(sale.quantity * sale.product.cost for sale in sales_in_range) # Assuming product.cost is available via relationship
    gross_profit = total_revenue - total_cost_of_goods_sold
    
    expenses_in_range = Expense.query.filter(
        Expense.business_id == user_business_id,
        Expense.date >= start_date_filter, # Changed expense_date to date
        Expense.date <= end_date_filter # Changed expense_date to date
    ).all()
    total_expenses = sum(expense.amount for expense in expenses_in_range)
    
    net_profit = total_revenue - total_expenses

    if total_revenue > 0:
        net_profit_percentage = (net_profit / total_revenue) * 100
    else:
        net_profit_percentage = 0.0


    # --- Sales by Product Report ---
    sales_by_product_query = db.session.query(
        Product.name,
        func.sum(Sale.quantity).label('total_quantity_sold'), # Changed quantity_sold to quantity
        func.sum(Sale.quantity * Sale.total_amount).label('total_revenue_from_product') # Changed quantity_sold to quantity and sale_price to total_amount
    ).join(Sale).filter(
        Sale.business_id == user_business_id,
        Sale.date >= start_date_filter, # Changed sale_date to date
        Sale.date <= end_date_filter # Changed sale_date to date
    ).group_by(Product.name).order_by(func.sum(Sale.quantity).desc()).all() # Changed quantity_sold to quantity
    
    sales_by_product = [{'product_name': s.name, 'quantity_sold': s.total_quantity_sold, 'revenue': s.total_revenue_from_product} 
                        for s in sales_by_product_query]

    # --- Expenses by Category Report ---
    expenses_by_category_query = db.session.query(
        Expense.category,
        func.sum(Expense.amount).label('total_amount')
    ).filter(
        Expense.business_id == user_business_id,
        Expense.date >= start_date_filter, # Changed expense_date to date
        Expense.date <= end_date_filter # Changed expense_date to date
    ).group_by(Expense.category).order_by(func.sum(Expense.amount).desc()).all()

    expenses_by_category = [{'category': e.category, 'total_amount': e.total_amount}
                            for e in expenses_by_category_query]

    # Get string representation for form fields (defaults or user selection)
    start_date_form = start_date_filter.strftime('%Y-%m-%d') if start_date_filter != datetime.datetime.min else ''
    end_date_form = end_date_filter.strftime('%Y-%m-%d') if end_date_filter != datetime.datetime.utcnow() else ''
    
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
                            now=datetime.datetime.utcnow()
                            )

@app.route('/init-db')
def init_db():
    with app.app_context():
        db.create_all()
    return "Database tables created!"

# --- Run the Application ---
if __name__ == '__main__':
    app.run(debug=True)
