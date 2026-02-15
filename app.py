from flask import Flask, render_template, request, redirect, jsonify
from config import *
from models import db, Product, Inventory, Bill, BillItem, Customer
from sklearn.linear_model import LinearRegression
import pandas as pd
from datetime import datetime

app = Flask(__name__)
app.config.from_object('config')
db.init_app(app)

with app.app_context():
    db.create_all()


@app.route('/')
def home():
    return redirect('/products')


@app.route('/products')
def products():
    return render_template('products.html', products=Product.query.all())


@app.route('/add_product', methods=['GET'])
def add_product_form():
    return render_template('add_product.html')


@app.route('/add_product', methods=['POST'])
def add_product():
    product = Product(
        name=request.form['name'],
        description=request.form['description'],
        price=float(request.form['price'])
    )
    db.session.add(product)
    db.session.commit()
    return redirect('/products')


@app.route('/inventory')
def inventory_page():
    inventory = Inventory.query.all()
    products = Product.query.all()
    return render_template('inventory.html', inventory=inventory, products=products)


@app.route('/add_inventory', methods=['POST'])
def add_inventory():
    inv = Inventory(
        product_id=request.form['product_id'],
        batch_no=request.form['batch_no'],
        quantity=int(request.form['quantity'])
    )
    db.session.add(inv)
    db.session.commit()
    return redirect('/inventory')


@app.route('/add_customer', methods=['POST'])
def add_customer():
    customer = Customer(
        name=request.form['name'],
        phone=request.form['phone']
    )
    db.session.add(customer)
    db.session.commit()
    return redirect('/billing')


def calculate_bill(items):
    subtotal = sum(item['price'] * item['qty'] for item in items)
    tax = round(subtotal * 0.18, 2)
    discount = round(subtotal * 0.05, 2)
    total = round(subtotal + tax - discount, 2)
    return subtotal, tax, discount, total


@app.route('/generate_bill', methods=['POST'])
def generate_bill():
    try:
        data = request.get_json()
        items = data.get('items', [])
        customer_id = int(data.get('customer_id'))

        if not items:
            return jsonify({"error": "No items selected"}), 400

        customer = Customer.query.get(customer_id)
        if not customer:
            return jsonify({"error": "Customer not found"}), 404

        subtotal, tax, discount, total = calculate_bill(items)

        bill = Bill(
            customer_id=customer_id,
            total_amount=total,
            tax=tax,
            discount=discount,
            created_at=datetime.utcnow()
        )
        db.session.add(bill)
        db.session.flush()

        for item in items:
            product_id = int(item['product_id'])
            qty = int(item['qty'])
            price = float(item['price'])

            inventory = Inventory.query.filter_by(product_id=product_id).order_by(Inventory.id.asc()).first()

            if not inventory or inventory.quantity < qty:
                db.session.rollback()
                return jsonify({"error": f"Insufficient stock for product ID {product_id}"}), 400

            inventory.quantity -= qty

            bill_item = BillItem(
                bill_id=bill.id,
                product_id=product_id,
                quantity=qty,
                price=price
            )
            db.session.add(bill_item)

        db.session.commit()
        return jsonify({"bill_id": bill.id, "total": total})

    except Exception as e:
        db.session.rollback()
        print("Billing Error:", str(e))
        return jsonify({"error": "Internal server error"}), 500


@app.route('/invoice/<int:bill_id>')
def invoice(bill_id):
    bill = Bill.query.get_or_404(bill_id)
    bill_items = BillItem.query.filter_by(bill_id=bill.id).all()
    customer = Customer.query.get_or_404(bill.customer_id)

    return render_template(
        'billing.html',
        bill=bill,
        bill_items=bill_items,
        customer=customer
    )


@app.route('/billing')
def billing_page():
    products = Product.query.all()
    customers = Customer.query.all()
    return render_template(
        'billing_form.html',
        products=products,
        customers=customers
    )


def forecast_sales(sales_df):
    sales_df = sales_df.reset_index(drop=True)
    sales_df['day'] = range(len(sales_df))
    model = LinearRegression()
    model.fit(sales_df[['day']], sales_df['sales'])
    future_day = pd.DataFrame([[len(sales_df) + 1]], columns=['day'])
    return model.predict(future_day)[0]


def calculate_reorder_level(avg_daily_sales, lead_time_days):
    return avg_daily_sales * lead_time_days


def is_suspicious_invoice(bill_total, avg_bill):
    return bill_total > avg_bill * 2


def recommend_products(customer_id):
    return Product.query.order_by(Product.id.desc()).limit(3).all()


if __name__ == "__main__":
    app.run(debug=True)
